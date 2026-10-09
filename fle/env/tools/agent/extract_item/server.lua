-- Helper function to check all possible inventories of an entity
--
-- LOCAL PATCH (P0-24, docs/02 §7.46 B): 原实现把 `entity.get_item_count(item_name)`
-- 放在「遍历 inventory 槽位」的循环体内累加 —— 但 `entity.get_item_count()` 返回的**本来就是
-- 该实体全部 inventory 的合计** ⇒ 同一个实体被按「它存在的槽位数 N」重复计数（实测石炉 N=7、
-- 木箱 N=2），使 available_count 虚高 N 倍；再经 `extract_count` → `player.insert(stack)`
-- 变成**凭空复制物品**（红线级：突破资源守恒）。
-- `entity.get_item_count(name)` 单次调用即为正确合计，且不依赖「哪些槽位存在」的枚举，
-- 故这里直接返回它（原 30 项 inventory_types 枚举已删除）。
local function get_entity_item_count(entity, item_name)
    return entity.get_item_count(item_name)
end

-- Helper function to remove items from any valid inventory
local function remove_items_from_entity(entity, stack)
    local inventory_types = {
        defines.inventory.chest,
        defines.inventory.furnace_source,
        defines.inventory.furnace_result,
        defines.inventory.assembling_machine_input,
        defines.inventory.assembling_machine_output,
        defines.inventory.fuel,
        defines.inventory.burnt_result,
        defines.inventory.reactor_source,
        defines.inventory.reactor_result,
        defines.inventory.lab_input,
        defines.inventory.lab_source,
        defines.inventory.mining_drill_input,
        defines.inventory.item_main,
        defines.inventory.robot_cargo,
        defines.inventory.robot_repair,
        defines.inventory.car_trunk,
        defines.inventory.car_fuel,
        defines.inventory.roboport_material,
        defines.inventory.roboport_robot,
        defines.inventory.storage_tank,
        defines.inventory.artillery_turret_ammo,
        defines.inventory.turret_ammo,
        defines.inventory.beacon_modules,
        defines.inventory.character_main,
        defines.inventory.character_guns,
        defines.inventory.character_ammo,
        defines.inventory.character_armor,
        defines.inventory.character_vehicle,
        defines.inventory.character_trash
    }

    local items_remaining = stack.count
    local total_removed = 0

    for _, inv_type in ipairs(inventory_types) do
        if items_remaining <= 0 then
            break
        end

        local inventory = entity.get_inventory(inv_type)
        if inventory then
            local current_stack = {name = stack.name, count = items_remaining}
            local removed = entity.remove_item(current_stack)
            total_removed = total_removed + removed
            items_remaining = items_remaining - removed
        end
    end

    return total_removed
end

storage.actions.extract_item = function(player_index, extract_item, count, x, y, source_name)
    -- Ensure we have a valid character, recreating if necessary
    local player = storage.utils.ensure_valid_character(player_index)
    local position = {x=x, y=y}
    local surface = player.surface

    -- First validate the request
    if count <= 0 then
        error("\"Invalid count: must be greater than 0\"")
    end

    -- Find all entities in range
    local search_radius = 10
    local area = {{position.x - search_radius, position.y - search_radius},
                  {position.x + search_radius, position.y + search_radius}}
    local buildings = nil

    if source_name ~= nil then
        buildings = surface.find_entities_filtered{
            area = area,
            name = source_name
        }
    else
        buildings = surface.find_entities_filtered{
            area = area
        }
    end

    -- Find the closest building with the item we want. Also remember the closest
    -- building overall, so we can tell "there is no such entity" apart from
    -- "the entity is right here, it just holds none of the requested item" -
    -- the old code used the same "entity not found" message for both cases,
    -- which made agents think a working furnace had been destroyed.
    local closest_distance = math.huge
    local closest_entity = nil
    local closest_any = nil
    local closest_any_distance = math.huge

    for _, building in ipairs(buildings) do
        if building.name ~= 'character' then
            local distance = ((position.x - building.position.x) ^ 2 +
                            (position.y - building.position.y) ^ 2) ^ 0.5
            if distance < closest_any_distance then
                closest_any_distance = distance
                closest_any = building
            end
            if get_entity_item_count(building, extract_item) > 0 and distance < closest_distance then
                closest_distance = distance
                closest_entity = building
            end
        end
    end

    -- Error handling in priority order

    if not closest_entity then
        if closest_any then
            -- Entity exists, it just contains none of the requested item.
            local where = "(" .. closest_any.position.x .. ", " .. closest_any.position.y .. ")"
            if source_name then
                error("\"Found a " .. source_name .. " at " .. where .. " but it contains no " .. extract_item .. " - use inspect_inventory to check what it holds, or put " .. extract_item .. " in first\"")
            else
                error("\"Found entities near " .. where .. " but none of them contain " .. extract_item .. "\"")
            end
        elseif source_name then
            error("\"Could not find any " .. source_name .. " within " .. search_radius .. " tiles of (" .. position.x .. ", " .. position.y .. ")\"")
        else
            error("\"Could not find any entities within " .. search_radius .. " tiles of (" .. position.x .. ", " .. position.y .. ")\"")
        end
    end

    if closest_distance > search_radius then
        error("\"Entity at ("..closest_entity.position.x..", "..closest_entity.position.y..") is too far away from your position of ("..player.position.x..","..player.position.y.."), move closer.\"")
    end

    -- Calculate how many items we can actually extract
    local available_count = get_entity_item_count(closest_entity, extract_item)
    local extract_count = math.min(count, available_count)

    -- Attempt the extraction
    local number_extracted = remove_items_from_entity(
        closest_entity, {name = extract_item, count = extract_count})

    if number_extracted > 0 then
        -- LOCAL PATCH (P0-24, docs/02 §7.46 B): 入包量必须等于**真实从实体移除的量**
        -- number_extracted。原实现写的是 `player.insert(stack)`，而 `stack.count` 是
        -- 「计划量」extract_count —— 只要它大于实体真实持有量，差额就被**凭空生成**
        -- （玩家白得物品，突破资源守恒）。回滚判断同样必须基于真实量，现已天然成立。
        local inserted = player.insert({name = extract_item, count = number_extracted})

        -- If we couldn't insert all items, put them back in the container
        if inserted < number_extracted then
            closest_entity.insert({name = extract_item, count = number_extracted - inserted})
            number_extracted = inserted
        end

        -- game.print("Extracted " .. number_extracted .. " " .. extract_item)
        return number_extracted
    else
        -- This should rarely happen given our prior checks
        error("\"Failed to extract " .. extract_item .. "\"")
    end
end