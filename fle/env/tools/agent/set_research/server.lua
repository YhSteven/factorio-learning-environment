storage.actions.set_research = function(player_index, technology_name)
    local player = storage.agent_characters[player_index]
    local force = player.force

    local tech = force.technologies[technology_name]
    if not tech then
        error(string.format("\"Technology %s does not exist\"", technology_name))
    end

    if tech.researched then
        error(string.format("\"Technology %s is already researched\"", technology_name))
    end

    if not tech.enabled then
        error(string.format("\"Technology %s is not enabled\"", technology_name))
    end

    local missing_prerequisites = {}
    for _, prerequisite in pairs(tech.prerequisites or {}) do
        if not prerequisite.researched then
            table.insert(missing_prerequisites, prerequisite.name)
        end
    end

    if #missing_prerequisites > 0 then
        table.sort(missing_prerequisites)
        error(string.format(
            "\"Cannot start research for %s. Missing prerequisites: %s\"",
            technology_name,
            table.concat(missing_prerequisites, ", ")
        ))
    end

    -- Only switch away from valid current research after validation succeeds.
    force.cancel_current_research()

    local success = force.add_research(technology_name)
    if not success then
        -- LOCAL PATCH (FLE defect #65, 2026-10-12):
        -- Factorio 2.0 ships **trigger-based** technologies (`prototype.research_trigger`):
        -- they can NOT be queued/set as the current research at all -- `add_research`
        -- always returns false for them -- and they unlock **automatically** once their
        -- trigger action is performed. This tree has 7 of them, and they are exactly the
        -- technologies that have no prerequisites, e.g.
        --     electronics   <- produce 10 x copper-plate
        --     steam-power   <- produce 50 x iron-plate
        --     steel-axe     <- produce 50 x steel-plate
        --     oil-processing / uranium-processing <- mine crude-oil / uranium-ore
        --     automation-science-pack <- craft 1 x lab (FLE pre-grants it in reset)
        -- Verified in-game: smelting copper/iron really does unlock them, so nothing is
        -- blocked -- the old opaque "Failed to start research for X" just hid the rule.
        -- Say what the model has to do instead. docs/02 §7.72 #65 (corrected).
        local proto = prototypes.technology[technology_name]
        local trig = proto and proto.research_trigger
        if trig then
            local item = nil
            if trig.item ~= nil then
                if type(trig.item) == "table" then
                    item = trig.item.name or trig.item[1]
                else
                    item = trig.item
                end
            end
            local what
            if trig.type == "craft-item" then
                what = string.format("produce %d x %s", trig.count or 1, tostring(item))
            elseif trig.type == "mine-entity" then
                what = string.format("mine %s (any amount)", tostring(trig.entity))
            elseif trig.type == "send-item-to-orbit" then
                what = string.format("send %s into orbit", tostring(item))
            else
                what = "complete its research trigger"
            end
            error(string.format(
                "\"%s is a TRIGGER-BASED technology: it cannot be queued as research and needs no science packs. Just complete its trigger and it unlocks automatically -- trigger: %s.\"",
                technology_name,
                what
            ))
        end
        local n_prereq = 0
        for _ in pairs(tech.prerequisites or {}) do n_prereq = n_prereq + 1 end
        if n_prereq == 0 then
            -- Unreachable for this tree (every 0-prerequisite technology is trigger-based),
            -- but keep a precise message in case a future/modded tree has a plain root tech.
            error(string.format(
                "\"Cannot start research for %s: it has no prerequisites and add_research() refused it (engine limitation). Choose a technology whose prerequisites are already researched.\"",
                technology_name
            ))
        end
        error(string.format("\"Failed to start research for %s\"", technology_name))
    end

    -- Collect and return the research ingredients
    local ingredients = {}
    local units_required = tech.research_unit_count

    for _, ingredient in pairs(tech.research_unit_ingredients) do
        table.insert(ingredients, {
            name = "\""..ingredient.name.."\"",
            count = ingredient.amount * units_required,
            type = ingredient.type
        })
    end

    return ingredients
end
