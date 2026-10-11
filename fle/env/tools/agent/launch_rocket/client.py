from typing import Union, cast

from fle.env.entities import Position, RocketSilo
from fle.env.game_types import Prototype
from fle.env.tools.agent.get_entity.client import GetEntity
from fle.env.tools import Tool


class LaunchRocket(Tool):
    def __init__(self, connection, game_state):
        super().__init__(connection, game_state)
        self.get_entity = GetEntity(connection, game_state)

    def __call__(self, silo: Union[Position, RocketSilo]) -> RocketSilo:
        """
        Launch a rocket.
        :param silo: Rocket silo
        :return: Your final position
        """

        if isinstance(silo, Position):
            position = silo
        else:
            position = silo.position

        try:
            # LOCAL PATCH (P0-21): client used to pass 3 arguments
            # (player_index, x, y) while the Lua action is `function(x, y)`.
            # Lua silently binds the extra first arg to x, so the silo lookup
            # ran at (player_index, position.x) instead of (position.x,
            # position.y) -- the launch always targeted the wrong place (and the
            # path was never exercised, so it stayed latent). Pass exactly the
            # two coordinates the Lua action expects.
            response, _ = self.execute(position.x, position.y)
            # LOCAL PATCH (#35/F3): server.lua returns `false` when there is no
            # rocket silo at the position, or the rocket is not ready to launch.
            # The client used to discard that verdict and unconditionally return
            # the silo, so a refused launch still looked successful (RCON showed
            # rockets_launched=0 / no space-science output). Surface the verdict
            # as an error instead -- a silent false success is worse than a
            # clear failure.
            if isinstance(response, str):
                raise Exception(
                    f"Cannot launch rocket. {self.get_error_message(response)}"
                )
            if not response:
                raise Exception(
                    f"Cannot launch rocket. No rocket silo at "
                    f"({position.x}, {position.y}) with a rocket ready to launch."
                )
            return cast(
                Prototype.RocketSilo, self.get_entity(Prototype.RocketSilo, position)
            )
        except Exception as e:
            raise Exception(f"Cannot launch rocket. {e}")
