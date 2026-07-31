-- puc_subset: tabele
local t = {10, 20, 30, a = 1}
assert(#t == 3)
assert(t[2] == 20)
assert(t.a == 1)
table.insert(t, 40)
assert(t[4] == 40)
local s = 0
for i, v in ipairs(t) do s = s + v end
assert(s == 100)
return "ok"
