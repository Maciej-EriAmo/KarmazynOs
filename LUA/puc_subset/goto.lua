-- puc: goto continue
local s = 0
for i = 1, 5 do
  if i % 2 == 0 then goto c end
  s = s + i
  ::c::
end
assert(s == 9)
return "ok"
