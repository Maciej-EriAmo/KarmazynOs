-- puc_subset: sandbox negatives
local ok = pcall(function() return string.dump(function() end) end)
assert(ok == false)
local f = load("return 1", "x", "b")
assert(f == nil)
return "ok"
