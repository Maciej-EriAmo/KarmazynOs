-- puc: pcall / xpcall
local ok, err = pcall(function() error("e") end)
assert(ok == false and err == "e")
local ok2, msg = xpcall(function() error("z") end, function(e) return "H:" .. e end)
assert(ok2 == false and msg == "H:z")
return "ok"
