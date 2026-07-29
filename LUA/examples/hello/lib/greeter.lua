local M = {}

function M.hello(name)
  name = name or "anon"
  return "witaj, " .. tostring(name)
end

return M
