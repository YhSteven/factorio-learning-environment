
-- Function to convert HSV to RGB
local function hsv_to_rgb(h, s, v)
    local r, g, b
    local i = math.floor(h * 6)
    local f = h * 6 - i
    local p = v * (1 - s)
    local q = v * (1 - f * s)
    local t = v * (1 - (1 - f) * s)
    
    i = i % 6
    
    if i == 0 then r, g, b = v, t, p
    elseif i == 1 then r, g, b = q, v, p
    elseif i == 2 then r, g, b = p, v, t
    elseif i == 3 then r, g, b = p, q, v
    elseif i == 4 then r, g, b = t, p, v
    elseif i == 5 then r, g, b = v, p, q
    end
    
    return {r = r, g = g, b = b, a = 1.0}
end

-- Function to generate a color based on the agent index
local function generate_agent_color(index, total_agents)
    local hue = (index - 1) / total_agents
    local saturation = 1.0
    local value = 1.0
    return hsv_to_rgb(hue, saturation, value)
end

-- Create agent characters script
storage.actions.create_agent_characters = function(num_agents, keep_all)
    -- LOCAL PATCH (keep_all): if the imported save carries a `character` entity
    -- (multiplayer saves do), reuse it instead of destroying every character and
    -- spawning a fresh one at the origin. Verified on 2026-10-12 that a
    -- single-player save hosted on a dedicated server carries NO character
    -- entity at all - its inventory lives in the owning player's record and
    -- belongs to that player, NOT to the agent - so the usual empty-spawn is
    -- correct there and nothing is inherited.
    -- ⚠️ UPSTREAM POLICY (user, 2026-10-12): local-only requirement
    -- ("continue from a save"), DO NOT PUSH UPSTREAM as-is.
    if keep_all and (tonumber(num_agents) or 1) == 1 then
        for _, entity in pairs(game.surfaces[1].find_entities_filtered{type = "character"}) do
            if entity and entity.valid then
                storage.agent_characters = {[1] = entity}
                player = entity
                -- Deliberately not touching `surface.always_day` here: that is a
                -- property of the imported world, not something we get to reset.
                return true
            end
        end
        -- No character entity in the save: fall through and build one the
        -- usual way (a brand-new player starts empty, as designed).
    end

    -- delete all character entities on the surface
    for _, entity in pairs(game.surfaces[1].find_entities_filtered{type = "character"}) do
        entity.destroy()
    end

    -- Initialize agent characters table
    for _, entity in pairs(game.surfaces[1].find_entities_filtered{type = "character"}) do
        entity.destroy()
    end
    -- Destroy existing agent characters if they exist
    if storage.agent_characters then
        for _, char in pairs(storage.agent_characters) do
            if char and char.valid then
                char.destroy()
            end
        end
        storage.agent_characters = {}
    end
    
    -- Create new characters for each agent
    for i = 1, num_agents do
        local char = game.surfaces[1].create_entity{
            name = "character",
            position = {x = 0, y = (i - 1) * 2},
            force = game.forces.player
        }
        
        -- Set colors for multi-agent scenarios
        if num_agents > 1 then
            char.color = generate_agent_color(i, num_agents)
        end
        
        storage.agent_characters[i] = char
    end

    -- Set the first character as the main player
    player = storage.agent_characters[1]
    player.surface.always_day=true
end