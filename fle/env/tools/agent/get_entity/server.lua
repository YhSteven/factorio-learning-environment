storage.actions.get_entity = function(player_index, entity, x, y)
    -- Ensure we have a valid character, recreating if necessary
    local player = storage.utils.ensure_valid_character(player_index)
    local position = {x=x, y=y}

    if prototypes.entity[entity] == nil then
        local name = entity:gsub(" ", "_"):gsub("-", "_")
        error(name .. " isnt something that exists. Did you make a typo? ")
    end

    local prototype = prototypes.entity[entity]
    -- LOCAL PATCH (FLE 缺陷 #7): 上游把 width/height 硬编码为 1，再用 3x3 区域取「最近的同名实体」，
    -- 所以「查询某格」会返回隔壁格的实体 —— 模型据此判断某格有没有带子必然出错
    -- （轨迹里 "entity already exists" 对撞的根源）。这里改为「该格是否真的被某个同名实体占据」：
    -- position 必须落在该实体**当前朝向**的包围盒内，否则宁可返回空。
    local collision_box = prototype.collision_box
    if collision_box == nil then
        -- 兜底：1x1
        collision_box = {left_top = {x = -0.5, y = -0.5}, right_bottom = {x = 0.5, y = 0.5}}
    end

    -- 搜索区：以查询格为中心、半边长取该原型碰撞箱四个分量的最大绝对值 ——
    -- 旋转只会交换 x/y 分量，因此这个正方形一定罩得住任意朝向下的实体占地。
    local reach = math.max(
        math.abs(collision_box.left_top.x), math.abs(collision_box.right_bottom.x),
        math.abs(collision_box.left_top.y), math.abs(collision_box.right_bottom.y)
    )
    local search_area = {
        {position.x - reach, position.y - reach},
        {position.x + reach, position.y + reach}
    }
    local entities = player.surface.find_entities_filtered{area = search_area, name = entity}

    -- 再按「实体**当前朝向**的包围盒是否真的包含查询格」过滤，排除只是擦边的邻居。
    -- 用 bounding_box（已按 direction 旋转）而不是原型碰撞箱：splitter 这类非方形实体
    -- 旋转后实际占地与未旋转原型不同。
    local function contains_position(building)
        local box = building.bounding_box
        return position.x >= box.left_top.x and position.x <= box.right_bottom.x
           and position.y >= box.left_top.y and position.y <= box.right_bottom.y
    end

    local closest_distance = math.huge
    local closest_entity = nil

    for _, building in ipairs(entities) do
        if building.name ~= 'character' and contains_position(building) then
            local distance = ((position.x - building.position.x) ^ 2 +
                            (position.y - building.position.y) ^ 2) ^ 0.5
            if distance < closest_distance then
                closest_distance = distance
                closest_entity = building
            end
        end
    end

    if closest_entity ~= nil then
        -- 返回的实体自带 position/dimensions，模型据此即可核对「请求格 vs 实体中心」，
        -- 因此不再额外回带 matched_position（避免给每个实体 repr 增加噪音字段）。
        return storage.utils.serialize_entity(closest_entity)
    else
        error("\"No entity of type " .. entity .. " found at the specified position.\"")
    end
end
