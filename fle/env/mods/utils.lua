-- utils.lua
storage.utils.remove_enemies = function ()
    game.forces["enemy"].kill_all_units()  -- Removes all biters
    game.map_settings.enemy_expansion.enabled = false  -- Stops biters from expanding
    game.map_settings.enemy_evolution.enabled = false  -- Stops biters from evolving
    local surface = game.surfaces[1]
    for _, entity in pairs(surface.find_entities_filtered({type="unit-spawner"})) do
        entity.destroy()
    end
end

local directions = {'north', 'northeast', 'east', 'southeast', 'south', 'southwest', 'west', 'northwest'}

storage.utils.get_direction = function(from_position, to_position)
    local dx = to_position.x - from_position.x
    local dy = to_position.y - from_position.y
    local adx = math.abs(dx)
    local ady = math.abs(dy)
    local diagonal_threshold = 0.5

    -- Factorio 2.0 direction values: north=0, northeast=2, east=4, southeast=6, south=8, southwest=10, west=12, northwest=14
    if adx > ady then
        if dx > 0 then
            return (ady / adx > diagonal_threshold) and (dy > 0 and 6 or 2) or 4  -- southeast/northeast or east
        else
            return (ady / adx > diagonal_threshold) and (dy > 0 and 10 or 14) or 12  -- southwest/northwest or west
        end
    else
        if dy > 0 then
            return (adx / ady > diagonal_threshold) and (dx > 0 and 6 or 10) or 8  -- southeast/southwest or south
        else
            return (adx / ady > diagonal_threshold) and (dx > 0 and 2 or 14) or 0  -- northeast/northwest or north
        end
    end
end

storage.utils.get_direction_with_diagonals = function(from_pos, to_pos)
    local dx = to_pos.x - from_pos.x
    local dy = to_pos.y - from_pos.y

    if dx == 0 and dy == 0 then
        return nil
    end

    -- Check for cardinal directions first
    local cardinal_margin = 0.20 --0.25
    if math.abs(dx) < cardinal_margin then
        return dy > 0 and defines.direction.south or defines.direction.north
    elseif math.abs(dy) < cardinal_margin then
        return dx > 0 and defines.direction.east or defines.direction.west
    end

    -- Handle diagonal directions
    if dx > 0 then
        return dy > 0 and defines.direction.southeast or defines.direction.northeast
    else
        return dy > 0 and defines.direction.southwest or defines.direction.northwest
    end
end


storage.utils.get_closest_entity = function(player, position)
    local closest_distance = math.huge
    local closest_entity = nil
    local entities = player.surface.find_entities_filtered{
        position = position,
        force = "player",
        radius = 5  -- Increased from 3 to 5 to better handle large entities like 3x3 drills
    }

    for _, entity in ipairs(entities) do
        if entity.name ~= 'character' and entity.name ~= 'laser-beam' then
            local distance = ((position.x - entity.position.x) ^ 2 + (position.y - entity.position.y) ^ 2) ^ 0.5
            if distance < closest_distance then
                closest_distance = distance
                closest_entity = entity
            end
        end
    end

    return closest_entity
end

storage.utils.calculate_movement_ticks = function(player, from_pos, to_pos)
    -- Calculate distance between points
    local dx = to_pos.x - from_pos.x
    local dy = to_pos.y - from_pos.y
    local distance = math.sqrt(dx * dx + dy * dy)

    -- Get player's walking speed (tiles per tick)
    -- Character base speed is 0.15 tiles/tick
    local walking_speed = player.character_running_speed
    if not walking_speed or walking_speed == 0 then
        walking_speed = 0.15  -- Default walking speed
    end

    -- Calculate ticks needed for movement
    return math.ceil(distance / walking_speed)
end

-- Wrapper around LuaSurface.can_place_entity that replicates all checks LuaPlayer.can_place_entity performs.
-- This allows our code to validate placement without relying on an actual LuaPlayer instance.
-- extra_params can be provided by callers to pass additional flags (e.g. fast_replace) if needed.
storage.utils.can_place_entity = function(player, entity_name, position, direction, extra_params)
    local params = extra_params or {}
    params.name = entity_name
    params.position = position
    params.direction = direction
    params.force = player.force
    -- Use the manual build-check path so the engine applies the same rules as when a human player builds.
    params.build_check_type = defines.build_check_type.manual
    return player.surface.can_place_entity(params)
end

storage.utils.avoid_entity = function(player_index, entity, position, direction)
    local player = storage.agent_characters[player_index]
    local player_position = player.position
    for i=0, 10 do
        local can_place = player.surface.can_place_entity{
            name = entity,
            force = "player",
            position = position,
            direction = storage.utils.get_entity_direction(entity, direction)
        }
        if can_place then
            return true
        end
        player.teleport({player_position.x + i, player_position.y + i})
    end
    player.teleport(player_position)
    return false
end

storage.crafting_queue = {}

script.on_event(defines.events.on_tick, function(event)
  -- Iterate over the crafting queue and update the remaining ticks
  for i, task in ipairs(storage.crafting_queue) do
    task.remaining_ticks = task.remaining_ticks - 1

    -- If the crafting is finished, consume the ingredients, insert the crafted entity, and remove the task from the queue
    if task.remaining_ticks <= 0 then
      for _, ingredient in pairs(task.recipe.ingredients) do
        task.player.remove_item({name = ingredient.name, count = ingredient.amount * task.count})
      end
      task.player.insert({name = task.entity_name, count = task.count})
      table.remove(storage.crafting_queue, i)
    end
  end
end)

-- Utility function to ensure a valid character exists for a given player index
-- Call this before any operation that needs the character
-- Returns the valid character entity, or creates a new one if invalid/missing
storage.utils.ensure_valid_character = function(player_index)
    if not storage.agent_characters then
        storage.agent_characters = {}
    end

    local char = storage.agent_characters[player_index]

    -- If character is missing or invalid, create a new one
    if not char or not char.valid then

        --if not char then
        --    error("Character not available")
        --end
        --if char.position and not char.valid then
        --    error("Character at: x="..char.position.x..", y="..char.position.y)
        --end
        --if not char.valid then
        --    error("Character not valid")
        --end

        local spawn_position = {x = 0, y = (player_index - 1) * 2}

        local new_char = game.surfaces[1].create_entity{
            name = "character",
            position = spawn_position,
            force = game.forces.player
        }

        if new_char then
            storage.agent_characters[player_index] = new_char
            return new_char
        else
            error("Failed to create agent character " .. player_index)
        end
    end

    return char
end

-- Serializes a value to the same format the Python client parses.
-- Accumulates parts in a table and concatenates once: repeated `s = s .. x`
-- reallocates the whole string per append, which made serializing large
-- tool responses (e.g. save_entity_state on big factories) O(N^2).
function dump(o)
   local parts = {}
   local function walk(v)
      if type(v) == 'table' then
         parts[#parts + 1] = '{ '
         for k, item in pairs(v) do
            if type(k) ~= 'number' then k = '"'..k..'"' end
            parts[#parts + 1] = '['..k..'] = '
            walk(item)
            parts[#parts + 1] = ','
         end
         parts[#parts + 1] = '} '
      else
         parts[#parts + 1] = tostring(v)
      end
   end
   walk(o)
   return table.concat(parts)
end

function storage.utils.inspect(player, radius, position)
    local surface = player.surface
    local bounding_box = {
        left_top = {x = position.x - radius, y = position.y - radius},
        right_bottom = {x = position.x + radius, y = position.y + radius}
    }

    local entities = surface.find_entities_filtered({bounding_box, force = "player"})
    local entity_data = {}

    for _, entity in ipairs(entities) do
        if entity.name ~= 'character' then
            local data = {
                name = entity.name:gsub("-", "_"),
                position = entity.position,
                direction = entity.direction,--directions[entity.direction+1],
                health = entity.health,
                force = entity.force.name,
                energy = entity.energy,
                status = entity.status,
                --crafted_items = entity.crafted_items or nil
            }

            -- Get entity contents if it has an inventory
            if entity.get_inventory(defines.inventory.chest) then
                local inventory = storage.utils.get_contents_compat(entity.get_inventory(defines.inventory.chest))
                data.contents = inventory
            end

            data.warnings = storage.utils.get_issues(entity)

            -- Get entity orientation if it has an orientation attribute
            if entity.type == "train-stop" or entity.type == "car" or entity.type == "locomotive" then
                data.orientation = entity.orientation
            end

            -- Get connected entities for pipes and transport belts
            if entity.type == "pipe" or entity.type == "transport-belt" then
                local path_ends = find_path_ends(entity)
                data.path_ends = {}
                for _, path_end in pairs(path_ends) do
                    local path_position = {x=path_end.position.x - player.position.x, y=path_end.position.y - player.position.y}
                    table.insert(data.path_ends, {name = path_end.name:gsub("-", "_"), position = path_position, unit_number = path_end.unit_number})
                end
            end

            table.insert(entity_data, data)
        else
            local data = {
                name = "player_character",
                position = entity.position,
                direction = directions[(entity.direction/2)+1],  -- Factorio 2.0 direction values are 0,2,4,6,8,10,12,14
            }
            table.insert(entity_data, data)
        end
    end

    -- Sort entities with path_ends by the length of path_ends in descending order
    table.sort(entity_data, function(a, b)
        if a.path_ends and b.path_ends then
            return #a.path_ends > #b.path_ends
        elseif a.path_ends then
            return true
        else
            return false
        end
    end)

    -- Remove entities that exist in the path_ends of other entities
    local visited_paths = {}
    local filtered_entity_data = {}
    for _, data in ipairs(entity_data) do
        if data.path_ends then
            local should_add = true
            for _, path_end in ipairs(data.path_ends) do
                if visited_paths[path_end.unit_number] then
                    should_add = false
                    break
                end
            end
            if should_add then
                for _, path_end in ipairs(data.path_ends) do
                    visited_paths[path_end.unit_number] = true
                end
                table.insert(filtered_entity_data, data)
            else
                data.path_ends = nil
                --table.insert(filtered_entity_data, data)
            end
        else
            table.insert(filtered_entity_data, data)
        end
    end
    entity_data = filtered_entity_data

    return entity_data
end

-- Format player inventory contents for error messages
storage.utils.format_inventory_for_error = function(player)
    local main_inv = player.get_inventory(defines.inventory.character_main)
    if not main_inv then
        return "empty"
    end

    local contents = storage.utils.get_contents_compat(main_inv)
    if not contents or next(contents) == nil then
        return "empty"
    end

    local items = {}
    for name, count in pairs(contents) do
        table.insert(items, name .. "=" .. count)
    end

    -- Limit to first 10 items to avoid overly long error messages
    if #items > 10 then
        local truncated = {}
        for i = 1, 10 do
            truncated[i] = items[i]
        end
        return table.concat(truncated, ", ") .. " (and " .. (#items - 10) .. " more)"
    end

    return table.concat(items, ", ")
end
-- LOCAL PATCH (FLE defect #61, 2026-10-12): underground-belt pairing.
-- `surface.create_entity` does **not** run the player-placement logic that pairs the two
-- halves of an underground belt: every half created through the tool chain stayed
-- `belt_to_ground_type = input` with `neighbours == nil`, so a bridge (the main way to
-- cross water / route around obstacles) could never be built by the agent
-- (docs/02 §7.70 / §7.72 #61).
-- Engine facts measured on 2.0.73 (state/tmp/_fix_probe_61*.py):
--   * the pair forms when the **second** half is created *facing* the first one
--     (opposite direction); the engine then flips the new half's direction back to the
--     travel direction, marks it `output`, and items really do transit (verified by
--     injecting coal into the input and reading it off the belt east of the output);
--   * `LuaEntity.belt_to_ground_type` is **read only** and `create_entity` silently
--     ignores a `belt_to_ground_type` parameter, so the direction used at creation time
--     is the only lever we have.
local UG_UNIT = {
    [defines.direction.north] = {x = 0, y = -1},
    [defines.direction.east] = {x = 1, y = 0},
    [defines.direction.south] = {x = 0, y = 1},
    [defines.direction.west] = {x = -1, y = 0},
}
local UG_OPPOSITE = {
    [defines.direction.north] = defines.direction.south,
    [defines.direction.east] = defines.direction.west,
    [defines.direction.south] = defines.direction.north,
    [defines.direction.west] = defines.direction.east,
}

-- Search `sign` tiles along `dir` from `position` for an unpaired half of the same belt.
local function ug_find_partner(surface, name, position, dir, sign)
    local unit = UG_UNIT[dir]
    if not unit then return nil end
    local proto = prototypes.entity[name]
    local maxd = (proto and proto.max_underground_distance) or 5
    for d = 1, maxd do
        local p = {
            x = position.x + unit.x * d * sign,
            y = position.y + unit.y * d * sign,
        }
        local e = surface.find_entity(name, p)
        if e and e.valid and e.type == "underground-belt" and not e.neighbours then
            return e
        end
    end
    return nil
end

local function ug_lanes_empty(e)
    for i = 1, 2 do
        local ok, line = pcall(function() return e.get_transport_line(i) end)
        if ok and line then
            if next(line.get_contents() or {}) ~= nil then return false end
        end
    end
    return true
end

-- Pair a freshly created underground belt and return the entity to serialise.
-- Whichever half has to "turn around" is destroyed and re-created in the opposite
-- direction; that is lossless because we only do it while the half is still unpaired
-- with both lanes empty. The engine then links the halves and normalises the output's
-- direction back to the travel direction.
function storage.utils.pair_underground_belt(player, name, created)
    if not created or not created.valid or created.type ~= "underground-belt" then
        return created
    end
    if created.neighbours then return created end
    local dir = created.direction
    if not UG_UNIT[dir] then return created end
    local pos = created.position
    -- (1) the near half already waits behind us -> turn around and face it
    if ug_find_partner(player.surface, name, pos, dir, -1) then
        created.destroy()
        return player.surface.create_entity{
            name = name,
            force = player.force,
            position = pos,
            direction = UG_OPPOSITE[dir],
        }
    end
    -- (2) the far half was placed first, ahead of us -> turn it around to face us
    local far = ug_find_partner(player.surface, name, pos, dir, 1)
    if far and ug_lanes_empty(far) then
        local fpos, fdir = far.position, far.direction
        far.destroy()
        player.surface.create_entity{
            name = name,
            force = player.force,
            position = fpos,
            direction = UG_OPPOSITE[fdir] or fdir,
        }
    end
    return created
end
