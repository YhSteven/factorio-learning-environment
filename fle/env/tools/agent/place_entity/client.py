from time import sleep

from fle.env.entities import Position, Entity
from fle.env import DirectionInternal, Direction
from fle.env.game_types import Prototype
from fle.env.tools.agent.get_entity.client import GetEntity
from fle.env.tools.agent.pickup_entity.client import PickupEntity
from fle.env.tools import Tool


class PlaceObject(Tool):
    def __init__(self, *args):
        super().__init__(*args)
        self.name = "place_entity"
        self.load()
        self.get_entity = GetEntity(*args)
        self.pickup_entity = PickupEntity(*args)

    def __call__(
        self,
        entity: Prototype,
        direction: Direction = Direction.UP,
        position: Position = Position(x=0, y=0),
        exact: bool = True,
        # relative=False
    ) -> Entity:
        """
        Places an entity e at local position (x, y) if you have it in inventory.
        :param entity: Entity to place
        :param direction: Cardinal direction to place
        :param position: Position to place entity
        :param exact: If True, place entity at exact position, else place entity at nearest possible position
        :return: Entity object
        """

        # if not isinstance(entity, Prototype):
        #    raise ValueError("The first argument must be a Prototype object")

        # If position is a tuple, cast it to a Position object:
        if isinstance(position, tuple):
            position = Position(x=position[0], y=position[1])

        if not isinstance(position, Position):
            raise ValueError("The position argument must be a Position object")

        if not isinstance(direction, (DirectionInternal, Direction)):
            raise ValueError("The second argument must be a Direction object")

        x, y = self.get_position(position)
        try:
            name, metaclass = entity.value
            while isinstance(metaclass, tuple):
                metaclass = metaclass[1]
        except Exception as e:
            raise Exception(f"Passed in {entity} argument is not a valid Prototype", e)

        factorio_direction = DirectionInternal.to_factorio_direction(direction)

        try:
            # If we are in `fast` mode, this is synchronous
            response, elapsed = self.execute(
                self.player_index, name, factorio_direction, x, y, exact
            )
        except Exception as e:
            # LOCAL PATCH (P0-14): 原内层 try 会把刚抛出的异常立刻再捕获 ⇒ 永远走兜底分支，
            # 可读原因被丢弃。这里直接保留 get_error_message 的结果。
            try:
                msg = self.get_error_message(str(e))
            except Exception:
                msg = str(e)
            raise Exception(f"Could not place {name} at ({x}, {y}), {msg}") from e

        # If we are in `slow` mode, there is a delay between placing the entity and the entity being created
        if not self.game_state.instance.fast:
            sleep(1)
            return self.get_entity(entity, position)
        else:
            if not isinstance(response, dict):
                # LOCAL PATCH (P0-14): 原来 split(":")[-1] 只取「最后一个冒号之后」的内容
                # （执行侧报错是纯字符串），于是 "No X in inventory. Current inventory:" 或
                # server.lua「有阻塞物: ...」的前缀被整段丢掉，只剩背包/后缀 ⇒ 报错不说原因。
                # 改用 get_error_message：只剥 Lua 源前缀与首尾引号，完整保留可读原因。
                try:
                    msg = self.get_error_message(str(response))
                except Exception:
                    msg = str(response).strip()
                raise Exception(f"Could not place {name} at ({x}, {y}), {msg}")

            cleaned_response = self.clean_response(response)

            try:
                object = metaclass(
                    prototype=entity.name, game=self.connection, **cleaned_response
                )
            except Exception as e:
                raise Exception(
                    f"Could not create {name} object from response (place entity): {cleaned_response}",
                    e,
                )

            return object
