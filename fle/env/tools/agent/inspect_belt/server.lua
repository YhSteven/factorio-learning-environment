-- LOCAL PATCH (2026-10-15) -- `inspect_belt`: structural belt-lane read-out.
-- See docs/02 §7.83 and docs/06 #73.
--
-- Why this exists: a transport belt carries two independent lanes, and the
-- rendered images cannot express them -- the full render puts a whole belt tile
-- into 16 px, so the two lanes are ~1.75 px apart. The data has always been
-- available here (get_transport_line), it just had no API surface.
--
-- Lane naming (verified empirically 2026-10-16, see docs/02 §7.83 F):
--   line 1 = the LEFT lane as seen by the traveller, line 2 = the RIGHT lane.
--   ("left" here is the belt's own left; e.g. the north half of an east belt.)
--   Method: a burner inserter dropping onto a belt lands on the far lane
--   (drop_position.y proved it), so a north-side inserter feeds line 2 and a
--   south-side inserter feeds line 1.
--
-- Read-only: this function never modifies the world.
storage.actions.inspect_belt = function(player_index, x, y, radius)
    local player = storage.utils.ensure_valid_character(player_index)
    local surface = player.surface

    local r = radius or 0
    if r < 0 then r = 0 end
    if r > 8 then r = 8 end

    local area = {
        {x - r - 0.5, y - r - 0.5},
        {x + r + 0.5, y + r + 0.5},
    }
    local belt_names = {
        "transport-belt", "fast-transport-belt", "express-transport-belt",
        "underground-belt", "fast-underground-belt", "express-underground-belt",
        "splitter", "fast-splitter", "express-splitter",
    }

    local found = surface.find_entities_filtered{
        area = area, force = "player", name = belt_names
    }

    local lanes_out = {}
    for _, e in ipairs(found) do
        local left, right = {}, {}
        local mixed = false
        for i = 1, 2 do
            local line = e.get_transport_line(i)
            local contents = line and storage.utils.get_contents_compat(line) or {}
            local kinds = 0
            for _ in pairs(contents) do kinds = kinds + 1 end
            if kinds > 1 then mixed = true end
            if i == 1 then left = contents else right = contents end
        end
        lanes_out[#lanes_out + 1] = {
            -- NOTE: keep this value hyphen-free. FLE's response transport mangles
            -- hyphenated *top-level string values* (they come back split, e.g.
            -- "fast-transport-belt" -> {name="fast", 1="belt"}), so a plain
            -- "fast_transport_belt" is the only shape that survives intact.
            belt_type = (e.name:gsub("-", "_")),
            x = e.position.x,
            y = e.position.y,
            direction = e.direction,
            left = left,
            right = right,
            mixed = mixed,
        }
    end

    table.sort(lanes_out, function(a, b)
        if a.y ~= b.y then return a.y < b.y end
        return a.x < b.x
    end)

    return { n = #lanes_out, belts = lanes_out }
end
