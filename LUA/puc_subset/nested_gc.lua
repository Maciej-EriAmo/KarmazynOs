-- puc: nested block survives collectgarbage (1.1.1+)
do
  local x = 99
  collectgarbage("collect")
  assert(x == 99)
end
return "ok"
