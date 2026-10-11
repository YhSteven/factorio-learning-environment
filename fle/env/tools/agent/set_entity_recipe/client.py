from typing import Any, Optional, Union

from fle.env.entities import Entity, Recipe
from fle.env.game_types import Prototype, RecipeName
from fle.env.tools import Tool


class SetEntityRecipe(Tool):
    def __init__(self, connection, game_state):
        super().__init__(connection, game_state)

    @staticmethod
    def _resolve_recipe_name(prototype: Any) -> Optional[str]:
        """LOCAL PATCH (#36/F4): normalise the many shapes a caller may pass.

        Previously only `Prototype` / `RecipeName` were accepted, so the most
        natural usage -- writing back the recipe you just read from the entity
        (`set_entity_recipe(asm, asm.recipe)`) -- raised
        `Invalid entity type: Recipe(...)`, and a plain recipe-name string
        raised `Invalid entity type: landfill`. Both are now accepted and
        reduced to the underlying Factorio recipe name.
        """
        if isinstance(prototype, Prototype):
            return prototype.value[0]
        if isinstance(prototype, RecipeName):
            return prototype.value
        if isinstance(prototype, Recipe):
            return prototype.name
        if isinstance(prototype, str):
            return prototype
        # Duck-typing fallback for future Recipe-like wrappers exposing `.name`.
        candidate = getattr(prototype, "name", None)
        return candidate if isinstance(candidate, str) else None

    def __call__(
        self, entity: Entity, prototype: Union[Prototype, RecipeName, Recipe, str]
    ) -> Entity:
        """
        Sets the recipe of an given entity.
        :param entity: Entity to set recipe
        :param prototype: The prototype to create, a recipe name for more
            complex processes, or the `Recipe` object read back from
            `entity.recipe`.
        :return: Entity that had its recipe set
        """

        x, y = entity.position.x, entity.position.y

        name = self._resolve_recipe_name(prototype)
        if name is None:
            # Distinct error class from "recipe does not exist" (see below).
            raise ValueError(
                f"Unsupported recipe argument type "
                f"{type(prototype).__name__}: {prototype!r}. Pass a Prototype, "
                f"RecipeName, Recipe, or a recipe-name string."
            )
        name = name.strip()
        if not name:
            raise ValueError("Recipe name must be a non-empty string.")

        response, elapsed = self.execute(self.player_index, name, x, y)

        if not isinstance(response, dict):
            # LOCAL PATCH (P0-21): 原写法有两处问题 —— ① split(":")[-1] 吞掉原因头部；
            # ② "set recipe to {name}" 与后缀之间**缺分隔符** ⇒ 文案粘连
            # （实测 `…iron-plateassembler needs a recipe first"`）。改用 get_error_message 并补冒号。
            reason = self.get_error_message(str(response))
            raise Exception(f"Could not set recipe to {name}: {reason}")

        cleaned_response = self.clean_response(response)

        # LOCAL PATCH (#36/F4): distinguish "the recipe does not exist" from a
        # genuine success. server.lua silently skips `set_recipe` when
        # `player.force.recipes[name]` is nil, so a bogus name used to look
        # exactly like a success. The serialized entity echoes the recipe that is
        # *actually* set, so compare it against what we asked for.
        applied = (cleaned_response.get("recipe") or {}).get("name")
        if applied is not None and applied.replace("_", "-") != name.replace("_", "-"):
            raise Exception(
                f"Could not set recipe to {name}: the recipe does not exist in "
                f"this game (the machine still uses '{applied}')."
            )

        # Find the matching Prototype
        matching_prototype = None
        for prototype in Prototype:
            if prototype.value[0] == cleaned_response["name"].replace("_", "-"):
                matching_prototype = prototype
                break

        if matching_prototype is None:
            print(
                f"Warning: No matching Prototype found for {cleaned_response['name']}"
            )
            raise Exception(f"Could not set recipe to {name}", response)

        metaclass = matching_prototype.value[1]

        entity = metaclass(**cleaned_response, prototype=matching_prototype)

        # Handle filter inserters differently
        if "filter" in entity.name:
            entity.filter = name  # Store the filter item
        else:
            entity.recipe = name  # Store the recipe for assembling machines

        return entity
