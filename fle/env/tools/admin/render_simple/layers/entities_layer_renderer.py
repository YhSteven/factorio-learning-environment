from typing import Dict, Callable
from PIL import ImageDraw

from fle.env.entities import Direction, EntityStatus
from fle.env.tools.admin.render_simple.layers.layer_renderer import LayerRenderer


def _lane_kinds(lane) -> int:
    try:
        return len(lane) if lane else 0
    except TypeError:
        return 0


def has_mixed_lane(entity) -> bool:
    """True when one belt lane under this entity carries more than one item type.

    LOCAL PATCH (2026-10-16, docs/02 §7.83 G).  A belt's two lanes are invisible
    in the drawn shapes (and a lane carrying two item types looks exactly like a
    single-item one), so this drives the magenta corner marker -- the only visual
    hint the schematic can give.  Runs over a BeltGroup's members too.
    """
    belts = getattr(entity, "belts", None)
    if belts:
        return any(has_mixed_lane(b) for b in belts)

    inventory = getattr(entity, "inventory", None)
    if not isinstance(inventory, dict):
        return False
    return any(_lane_kinds(inventory.get(lane)) > 1 for lane in ("left", "right"))


class EntitiesLayerRenderer(LayerRenderer):
    """Renderer for player-built entities"""

    def __init__(self, config, categorizer, color_manager, shape_renderer):
        super().__init__(config)
        self.categorizer = categorizer
        self.color_manager = color_manager
        self.shape_renderer = shape_renderer

    @property
    def layer_name(self) -> str:
        return "entities"

    def render(
        self,
        draw: ImageDraw.ImageDraw,
        game_to_img_func: Callable,
        boundaries: Dict[str, float],
        **kwargs,
    ) -> None:
        """Draw all entities on the map with their shapes, directions, and status indicators"""
        entities = kwargs.get("entities", [])
        if not entities:
            return

        for entity in entities:
            # Get entity position and dimensions
            pos = entity.position

            width = (
                entity.tile_dimensions.tile_width
                if hasattr(entity, "tile_dimensions")
                else 1
            )
            height = (
                entity.tile_dimensions.tile_height
                if hasattr(entity, "tile_dimensions")
                else 1
            )

            if entity.direction.value in (Direction.LEFT.value, Direction.RIGHT.value):
                width1 = width
                width = height
                height = width1

            # Calculate rectangle coordinates
            x1, y1 = game_to_img_func(pos.x - width / 2, pos.y - height / 2)
            x2, y2 = game_to_img_func(pos.x + width / 2, pos.y + height / 2)

            # Get entity color and category
            entity_color = self.color_manager.get_entity_color(entity)
            category = self.categorizer.get_entity_category(entity)
            shape_type = self.config.get_category_shape(category)

            # Draw entity sprite/shape
            self.shape_renderer.draw_shape(
                draw,
                x1,
                y1,
                x2,
                y2,
                shape_type,
                entity_color,
                # entity_name=getattr(entity, 'name', None),
                direction=entity.direction if hasattr(entity, "direction") else None,
            )

            # Add status indicator in corner if enabled.
            # The top-left corner is reserved for real entity statuses; the
            # mixed-belt-lane marker goes to the TOP-RIGHT so it never displaces
            # them (user, 2026-10-16). Both are explained in the legend.
            if (
                self.config.style["status_indicator_enabled"]
                and entity.status != EntityStatus.NORMAL
            ):
                self.shape_renderer.draw_status_indicator(
                    draw, x1, y1, x2, y2, entity.status
                )

            if has_mixed_lane(entity):
                self.shape_renderer.draw_status_indicator(
                    draw, x1, y1, x2, y2, entity.status,
                    color=self.config.style.get("mixed_lane_color", (255, 0, 200)),
                    corner="right",
                )

            # Add direction indicator if enabled
            if self.config.style["direction_indicator_enabled"] and hasattr(
                entity, "direction"
            ):
                self.shape_renderer.draw_direction_indicator(
                    draw, x1, y1, x2, y2, entity.direction
                )
