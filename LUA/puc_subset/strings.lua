-- puc_subset: string
assert(string.sub("abcdef", 2, 4) == "bcd")
assert(string.format("%05d", 7) == "00007")
assert(string.rep("ab", 3) == "ababab")
local n = 0
for w in string.gmatch("a b c", "%S+") do n = n + 1 end
assert(n == 3)
return "ok"
