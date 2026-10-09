from time import sleep

from fle.env.entities import Position, Entity

from fle.env.game_types import Prototype
from fle.env.tools.agent.get_entities.client import GetEntities
from fle.env.tools import Tool


class GetEntity(Tool):
    def __init__(self, connection, game_state):
        super().__init__(connection, game_state)
        self.get_entities = GetEntities(connection, game_state)

    def __call__(self, entity: Prototype, position: Position) -> Entity:
        """
        Retrieve a given entity object at position (x, y) if it exists on the world.

        Semantics (LOCAL PATCH, FLE defect #7): 'at position' means the position is
        covered by that entity's own collision box, i.e. the cell is occupied by an
        entity of this prototype. It does NOT return the nearest entity of the same
        prototype within 3x3 tiles (upstream behaviour), which made it impossible to
        tell whether a given cell is actually free.

        :param entity: Entity prototype to get, e.g Prototype.StoneFurnace
        :param position: Position where to look
        :return: Entity object, or None when that cell holds no such entity
        """
        assert isinstance(entity, Prototype)
        assert isinstance(position, Position)
        if entity == Prototype.BeltGroup:
            entities = self.get_entities(
                {
                    Prototype.TransportBelt,
                    Prototype.FastTransportBelt,
                    Prototype.ExpressTransportBelt,
                },
                position=position,
            )
            return entities[0] if len(entities) > 0 else None
        elif entity == Prototype.PipeGroup:
            entities = self.get_entities({Prototype.Pipe}, position=position)
            return entities[0] if len(entities) > 0 else None
        elif entity == Prototype.ElectricityGroup:
            entities = self.get_entities(
                {
                    Prototype.SmallElectricPole,
                    Prototype.MediumElectricPole,
                    Prototype.BigElectricPole,
                },
                position=position,
            )
            return entities[0] if len(entities) > 0 else None
        else:
            x, y = self.get_position(position)
            name, metaclass = entity.value
            while isinstance(metaclass, tuple):
                metaclass = metaclass[1]

            sleep(0.05)
            response, elapsed = self.execute(self.player_index, name, x, y)

            if isinstance(response, str):
                # LOCAL PATCH (P0-21): 原来把「Lua 报错串」与「该格无实体」一律
                # return None —— 真正的执行错误（原型不存在、内部异常）被静默吞成
                # 「这格没有实体」，模型据此判断空格/被毁，属 A5 同族。
                # 只有 Lua 明说的「该格无此实体」才返回 None（FLE 缺陷 #7 语义），
                # 其余错误串一律抛出并保留完整原因。
                msg = self.get_error_message(response)
                if "found at the specified position" in msg:
                    return None
                raise Exception(f"Could not get {name} at ({x}, {y}): {msg}")

            if response is None or response == {}:
                # No entity found at position - return None instead of raising
                return None

            cleaned_response = self.clean_response(response)
            try:
                object = metaclass(prototype=entity.name, **cleaned_response)
            except Exception as e:
                raise Exception(
                    f"Could not create {name} object from response (get entity): {cleaned_response}",
                    e,
                )

            return object
