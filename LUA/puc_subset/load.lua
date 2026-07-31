-- puc: load text only
local f = load("return 2+2", "t")
assert(f and f() == 4)
local b = load("return 1", "n", "b")
assert(b == nil)
return "ok"
