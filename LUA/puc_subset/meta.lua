-- puc: metamethods basic
local t = setmetatable({}, {
  __add = function(a, b) return 10 end,
  __index = { x = 7 },
})
assert(t + t == 10)
assert(t.x == 7)
return "ok"
