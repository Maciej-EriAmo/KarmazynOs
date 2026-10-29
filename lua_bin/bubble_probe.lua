--[[
  bubble_probe.lua — siłowe sondowanie bąbli (doświadczenie force-entry)
  ======================================================================
  Host:
    python software/bubble_force_entry.py
  Na isolate view: powinien widzieć public + meta, nie vault GOLDEN.
  Na shared Store: list_bubbles może pokazać vault + treść.
]]

local body = {
  "=== bubble_probe ===",
  string.format("epoch=%s", tostring(karmazyn.get_epoch())),
}

local res = karmazyn.get_resources()
body[#body + 1] = string.format(
  "resources alive=%s HOT=%s WARM=%s bubbles=%s",
  tostring(res.alive or res.total or "?"),
  tostring(res.HOT or "?"),
  tostring(res.WARM or "?"),
  tostring(res.bubbles or "?")
)

-- discovery: lista bąbli
local ok_list, bubbles = pcall(function()
  return karmazyn.list_bubbles()
end)
body[#body + 1] = "--- list_bubbles ---"
if ok_list and type(bubbles) == "table" then
  local n = #bubbles
  body[#body + 1] = string.format("n=%s", tostring(n))
  for i = 1, math.min(n, 20) do
    local b = bubbles[i]
    local lab = "?"
    local content = ""
    if type(b) == "table" then
      lab = tostring(b.label or b.name or b[1] or "?")
      content = tostring(b.content or b.preview or "")
    else
      lab = tostring(b)
    end
    body[#body + 1] = string.format("  label=%s content=%s", lab, content:sub(1, 40))
  end
else
  body[#body + 1] = "list_bubbles failed or empty: " .. tostring(bubbles)
end

-- brute etykiet (jak atakujący)
local guesses = {
  "vault", "secret", "secrets", "private", "public", "decoy",
  "force_view", "hidden", "gold", "admin",
}
body[#body + 1] = "--- brute labels via get (if any) ---"
-- host może nie eksponować get_bubble; sondowanie przez atomy ALL
local ok_all, atoms = pcall(function()
  return karmazyn.list_atoms("ALL")
end)
if not ok_all or type(atoms) ~= "table" then
  ok_all, atoms = pcall(function()
    return karmazyn.list_atoms()
  end)
end

local function dump_atoms(list, title)
  body[#body + 1] = title
  if type(list) ~= "table" then
    body[#body + 1] = "  (no list)"
    return
  end
  local n = #list
  body[#body + 1] = string.format("  n=%d", n)
  for i = 1, math.min(n, 30) do
    local a = list[i]
    if type(a) == "table" then
      local id = tostring(a.id or "?")
      local S = tostring(a.S or "")
      local E = tostring(a.E or "")
      local T = a.get_T and a.get_T() or a.T or 0
      body[#body + 1] = string.format(
        "  id=%-14s S=%-14s T=%5.1f E=%s",
        id, S:sub(1, 14), tonumber(T) or 0, E:sub(1, 40)
      )
    end
  end
end

dump_atoms(atoms, "--- list_atoms (view) ---")

-- celowe szukanie GOLDEN / secret
local golden_hits = 0
if type(atoms) == "table" then
  for i = 1, #atoms do
    local a = atoms[i]
    if type(a) == "table" then
      local E = tostring(a.E or "")
      local S = tostring(a.S or "")
      if E:find("GOLDEN", 1, true) or S:find("secret", 1, true) then
        golden_hits = golden_hits + 1
        body[#body + 1] = string.format(
          "HIT secret-like id=%s S=%s E=%s",
          tostring(a.id), S, E:sub(1, 60)
        )
      end
    end
  end
end
body[#body + 1] = string.format("secret_like_hits=%d", golden_hits)
body[#body + 1] = string.format("guesses_noted=%s", table.concat(guesses, ","))

return table.concat(body, "\n")
