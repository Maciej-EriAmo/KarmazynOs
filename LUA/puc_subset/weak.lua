-- puc: weak values (guest GC)
local h = {}
setmetatable(h, { __mode = "v" })
local function drop()
  h.k = { n = 1 }
end
drop()
collectgarbage("collect")
assert(h.k == nil)
return "ok"
