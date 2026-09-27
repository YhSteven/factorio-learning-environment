-- Make solid ore prototypes infinite so patches never deplete.
-- Only `infinite` and `minimum` are touched: map-gen placement/amounts
-- stay identical (same seed -> same map), verified by tile/amount scan.
local ores = { "iron-ore", "copper-ore", "stone", "coal", "uranium-ore" }

for _, name in ipairs(ores) do
  local r = data.raw["resource"][name]
  if r then
    r.infinite = true
    -- matches current map richness (10,000 per tile); lower this to let
    -- patches slowly drain toward the floor instead of staying full
    r.minimum = 10000
  end
end
