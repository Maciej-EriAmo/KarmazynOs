-- puc: multi-return / assign
local function f() return 1, 2, 3 end
local a, b, c = f()
assert(a == 1 and b == 2 and c == 3)
local x = (f())
assert(x == 1)
return "ok"
