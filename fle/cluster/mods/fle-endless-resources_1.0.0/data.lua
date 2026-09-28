-- Make solid ore prototypes infinite so patches never deplete.
-- Only `infinite` and `minimum` are touched: map-gen placement/amounts
-- stay identical (same seed -> same map), verified by tile/amount scan.
local ores = { "iron-ore", "copper-ore", "stone", "coal", "uranium-ore" }

for _, name in ipairs(ores) do
  local r = data.raw["resource"][name]
  if r then
    r.infinite = true
    -- ★ 必须与 minimum 一起设置：infinite 资源产出率 = amount/normal，
    -- 原型原为 finite 时 normal 缺省 = 1 → 补矿到 10000 后钻头单次产出
    -- 10000 个矿（实测 2026-09-28，PS 虚增 61000）。normal=10000 → 恒 100% 产率。
    r.normal = 10000
    r.minimum = 10000
  end
end
