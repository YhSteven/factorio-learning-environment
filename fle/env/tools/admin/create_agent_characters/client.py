from fle.env.tools import Tool


class CreateAgentCharacters(Tool):
    def __init__(self, connection, game_state):
        super().__init__(connection, game_state)

    def __call__(self, num_agents: int, keep_all: bool = False) -> bool:
        """
        Creates an agent character

        Args:
            keep_all: LOCAL PATCH - if the imported save carries a `character`
                entity, reuse it instead of destroying it and building a fresh
                one at the origin. Saves hosted without their owning player
                carry no character entity at all (the inventory belongs to the
                save's player record, not to the agent), in which case a
                brand-new empty character is spawned as upstream does.
        """
        # LOCAL PATCH (keep_all): see docs/02 §7.68.
        # ⚠️ UPSTREAM POLICY (user, 2026-10-12): this serves our own
        # "continue from a save" requirement - keep locally, DO NOT PUSH
        # UPSTREAM as-is.
        response, elapsed = self.execute(num_agents, keep_all)
        return True
