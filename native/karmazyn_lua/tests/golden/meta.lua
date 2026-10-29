local t = {}
setmetatable(t, { __index = function() return 7 end })
return t.a
