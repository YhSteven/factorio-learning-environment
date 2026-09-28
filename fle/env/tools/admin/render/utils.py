"""Utility functions for the rendering system."""

import json
import base64
import zlib
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Union

from fle.env import (
    Entity,
    EntityGroup,
    WallGroup,
    BeltGroup,
    PipeGroup,
    ElectricityGroup,
    EntityCore,
)
from .constants import (
    DEFAULT_MAX_RESOURCE_AMOUNT,
    MIN_RESOURCE_VOLUME,
    MAX_RESOURCE_VOLUME,
    DEFAULT_RESOURCE_VARIANTS,
)


def flatten_entities(
    entities: List[Union[Dict, Entity, EntityGroup]],
) -> List[Union[Entity, EntityCore]]:
    # ⚠️ 本地补丁（local-patches，2026-09-28）：删除上游的
    #   「先求 max_direction，若 > 6 则把所有 direction 除以 2」启发式。
    # 理由（均有实测支撑）：
    #   1) FLE 自己的 Direction 就是 16 向（NORTH=0 / EAST=4 / SOUTH=8 / WEST=12，对角 2/6/10/14），
    #      EntityCore 也按 Direction 校验 ⇒ 传进来的合法值本就在 FLE 空间内，除以 2 只会改错语义。
    #   2) 该启发式**无条件**生效：真实局只要有任一南/西向实体（max>6），东向的 4 就变成 2，
    #      而 `renderers/*.py` 有 19 处硬查 `DIRECTIONS[direction]`（只认 0/4/8/12）
    #      → `KeyError: 2` → `_render` 抛异常 → 上层静默退回 `_render_simple`。
    #   3) `direction / 2` 还是 float（4/2=2.0），会再撞上 transport_belt 之类
    #      `if not isinstance(direction, int): direction = direction.value` 分支 → AttributeError。
    #   4) 真正的非 FLE 编码（如 0-3）除以 2 之后依然不是合法 Direction，救不回来
    #      ⇒ 这条启发式没有任何能成立的场景，故整段移除。
    for entity in entities:
        if isinstance(entity, dict):
            if "direction" not in entity:
                entity["direction"] = 0

    for entity in entities:
        if isinstance(entity, dict):
            try:
                yield EntityCore(**entity)
            except Exception:
                pass
        elif isinstance(entity, EntityGroup):
            e_list = []
            if isinstance(entity, WallGroup):
                e_list = entity.entities
            elif isinstance(entity, BeltGroup):
                e_list = entity.belts
            elif isinstance(entity, PipeGroup):
                e_list = entity.pipes
            elif isinstance(entity, ElectricityGroup):
                e_list = entity.poles

            for e in e_list:
                yield e
        else:
            # if entity.name == "character":
            #    continue

            yield entity


def entities_to_grid(entities: List[Union[Dict, Entity]]) -> Dict:
    """Convert entity list to position grid."""
    grid = {}
    for entity in entities:
        if isinstance(entity, dict):
            x = entity["position"]["x"]
            y = entity["position"]["y"]
            if x not in grid:
                grid[x] = {}
            grid[x][y] = entity
        elif isinstance(entity, EntityGroup):
            e_list = []
            if isinstance(entity, WallGroup):
                e_list = entity.entities
            elif isinstance(entity, BeltGroup):
                e_list = entity.belts
            elif isinstance(entity, PipeGroup):
                e_list = entity.pipes
            elif isinstance(entity, ElectricityGroup):
                e_list = entity.poles

            for e in e_list:
                if e.position.x not in grid:
                    grid[e.position.x] = {}
                grid[e.position.x][e.position.y] = entity

        elif isinstance(entity, EntityCore):
            x = entity.position.x
            y = entity.position.y
            if x not in grid:
                grid[x] = {}
            grid[x][y] = entity

    return grid


def resources_to_grid(resources: List[Dict]) -> Dict:
    """Convert resource list to position grid."""
    grid = {}
    for resource in resources:
        x = resource["position"]["x"]
        y = resource["position"]["y"]
        if x not in grid:
            grid[x] = {}
        grid[x][y] = resource
    return grid


def get_resource_variant(
    x: float, y: float, max_variants: int = DEFAULT_RESOURCE_VARIANTS
) -> int:
    """
    Calculate resource variant based on position using a hash-like function.
    Returns a variant number from 1 to max_variants.
    """
    hash_value = int(x * 7 + y * 13) % max_variants
    return hash_value + 1  # Variants are 1-indexed


def get_resource_volume(
    amount: int, max_amount: int = DEFAULT_MAX_RESOURCE_AMOUNT
) -> int:
    """
    Calculate resource volume level (1-8) based on amount.
    8 = full, 1 = nearly empty
    """
    if amount <= 0:
        return MIN_RESOURCE_VOLUME

    percentage = min(amount / max_amount, 1.0)
    volume = max(
        MIN_RESOURCE_VOLUME,
        min(MAX_RESOURCE_VOLUME, int(percentage * MAX_RESOURCE_VOLUME)),
    )
    return volume


def is_entity(entity: Optional[Dict], target: str) -> bool:
    """Check if entity matches target name."""
    if entity is None:
        return False
    return entity.get("name") == target


def is_entity_in_direction(entity: Optional[Dict], target: str, direction: int) -> bool:
    """Check if entity matches target name and direction."""
    if not is_entity(entity, target):
        return False
    return entity.get("direction", 0) == direction


def recipe_has_fluids(recipe: Dict) -> bool:
    """Check if recipe has fluid ingredients."""
    ingredients = recipe.get("ingredients") or recipe.get("normal", {}).get(
        "ingredients", []
    )
    return any(ing.get("type") == "fluid" for ing in ingredients)


def is_tree_entity(entity_name: str) -> bool:
    """Check if an entity is a tree."""
    return (
        entity_name.startswith("tree-")
        or "dead-tree" in entity_name
        or "dry-tree" in entity_name
        or "dead-grey-trunk" in entity_name
    )


def is_rock_entity(entity_name: str) -> bool:
    return "rock-" in entity_name


def parse_blueprint(blueprint_string: str) -> Dict:
    """Parse blueprint string to JSON."""
    decoded = base64.b64decode(blueprint_string[1:])
    unzipped = zlib.decompress(decoded)
    return json.loads(unzipped)


def load_game_data(data_path: str) -> Tuple[Dict, Dict]:
    """Load game data from JSON file."""
    with open(data_path, "r") as f:
        data = json.load(f)

    parsed = {}
    recipes = {}

    skip_categories = [
        "technology",
        "item-subgroup",
        "tutorial",
        "simple-entity",
        "unit",
        "simple-entity-with-force",
        "rail-remnants",
        "item-group",
        "particle",
        "car",
        "font",
        "character-corpse",
        "cargo-wagon",
        "ammo-category",
        "ambient-sound",
        "smoke",
        "tree",
        "corpse",
    ]

    for category, items in data.items():
        if category in skip_categories or category.endswith("achievement"):
            continue

        try:
            for entity_name, entity_data in items.items():
                if category == "recipe":
                    recipes[entity_name] = entity_data
                else:
                    parsed[entity_name] = entity_data
        except AttributeError:
            pass

    return parsed, recipes


def find_fle_sprites_dir() -> Path:
    """Walk up the directory tree until we find .fle directory.

    Also checks common locations if cwd-based search fails.
    """
    import logging
    import os

    logger = logging.getLogger(__name__)

    # First, try walking up from cwd
    current = Path.cwd()
    start_cwd = current

    while current != current.parent:
        sprites_dir = current / ".fle" / "sprites"
        if sprites_dir.exists():
            logger.debug(f"Found sprites directory at {sprites_dir}")
            return sprites_dir
        current = current.parent

    # Try common fallback locations
    fallback_paths = [
        # Home directory
        Path.home() / ".fle" / "sprites",
        # Environment variable if set
        Path(os.environ.get("FLE_SPRITES_DIR", ""))
        if os.environ.get("FLE_SPRITES_DIR")
        else None,
        # Relative to the fle package (this file is in fle/env/tools/admin/render/utils.py)
        # Go up 5 levels to get from render/ -> admin/ -> tools/ -> env/ -> fle/ -> project_root/
        Path(__file__).parent.parent.parent.parent.parent.parent / ".fle" / "sprites",
    ]

    for fallback in fallback_paths:
        if fallback and fallback.exists():
            logger.info(f"Using fallback sprites directory: {fallback}")
            return fallback

    logger.warning(
        f"Sprites not found (searched from {start_cwd} to root and fallback locations). "
        f"Vision rendering will produce empty images. "
        f"Run 'fle sprites' to download, or set FLE_SPRITES_DIR."
    )

    # Fallback - return the path even if it doesn't exist
    return Path.cwd() / ".fle" / "sprites"
