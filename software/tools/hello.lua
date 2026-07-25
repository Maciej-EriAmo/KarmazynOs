-- tools/hello.lua — przykładowe narzędzie KarmazynOS (package.preload.hello)
local M = {}

function M.run(name)
  name = name or "magos"
  return "witaj, " .. tostring(name) .. " — z narzędzia hello"
end

function M.version()
  return "0.1"
end

return M
