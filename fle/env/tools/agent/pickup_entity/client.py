from typing import Union, Optional

from fle.env import entities as ent
from fle.env.game_types import Prototype
from fle.env.tools import Tool


class PickupEntity(Tool):
    def __init__(self, *args):
        super().__init__(*args)

    def __call__(
        self,
        entity: Union[ent.Entity, Prototype, ent.EntityGroup],
        position: Optional[ent.Position] = None,
    ) -> bool:
        """
        Pick up an entity if it exists on the world at a given position.
        :param entity: Entity prototype to pickup, e.g Prototype.IronPlate
        :param position: Position to pickup entity
        :return: True if the entity was picked up successfully, False otherwise.
        """
        if not isinstance(entity, (Prototype, ent.Entity, ent.EntityGroup)):
            raise ValueError("The first argument must be an Entity or Prototype object")
        if isinstance(entity, ent.Entity) and isinstance(position, ent.Position):
            raise ValueError(
                "If the first argument is an Entity object, the second argument must be None"
            )
        if position is not None and not isinstance(position, ent.Position):
            raise ValueError("The second argument must be a Position object")

        if isinstance(entity, Prototype):
            name, _ = entity.value
        else:
            name = entity.name
            if isinstance(entity, ent.BeltGroup):
                belts = entity.belts
                for belt in belts:
                    resp = self.__call__(belt)
                    if not resp:
                        return False
                return True
            elif isinstance(entity, ent.PipeGroup):
                pipes = entity.pipes
                for pipe in pipes:
                    resp = self.__call__(pipe)
                    if not resp:
                        return False
                return True

            elif isinstance(entity, ent.ElectricityGroup):
                poles = entity.poles
                for pole in poles:
                    resp = self.__call__(pole)
                    if not resp:
                        return False
                return True

        if position:
            x, y = position.x, position.y
            response, elapsed = self.execute(self.player_index, x, y, name)
        elif isinstance(entity, ent.UndergroundBelt):
            # LOCAL PATCH (#40/F7): an underground belt is a single 1x2 entity.
            # Its `.output_position` is the cell it *feeds* (the paired exit, or
            # centre+offset when it has no neighbour) -- it does NOT necessarily
            # hold another underground-belt. The old code *required* both probes
            # to succeed, so picking up a lone belt raised
            #   "Couldn't find underground-belt at (-19.5, 21.5)"
            # AFTER the belt at `.position` (-19.5, 22.5) had already been
            # removed -- a false failure (the tool reported failure while the
            # item was already back in the inventory). Probe both cells but only
            # fail when NEITHER removes anything.
            candidates = [(entity.position.x, entity.position.y)]
            output_position = getattr(entity, "output_position", None)
            if output_position is not None and (
                output_position.x,
                output_position.y,
            ) != candidates[0]:
                candidates.append((output_position.x, output_position.y))

            picked = False
            last_error = None
            for px, py in candidates:
                probe, elapsed = self.execute(self.player_index, px, py, name)
                if probe == 1 or probe == {}:
                    picked = True
                elif last_error is None:
                    last_error = self.get_error_message(probe)
            if not picked:
                raise Exception(f"Could not pickup: {last_error}")
            response = {}

        elif isinstance(entity, ent.Entity):
            x, y = entity.position.x, entity.position.y
            response, elapsed = self.execute(self.player_index, x, y, name)
        else:
            raise ValueError("The second argument must be a Position object")

        if response != 1 and response != {}:
            raise Exception(f"Could not pickup: {self.get_error_message(response)}")
        return True
