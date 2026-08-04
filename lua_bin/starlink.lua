--[[
  starlink.lua — OS surface: Starlink catalog view
  ================================================
  Host (isolated view Store — default):
    python software/starlink_atoms.py --limit 0 --prop sgp4 --hot-only --lua
  Shared catalog Store (debug): --lua-shared
  Docs: Documents/STARLINK_ATOMS.md
]]

local function parse_meta_E(e)
  -- format: sats=N;cells=N;hot=N;warm=N;prop=...;hot_only=0|1;...;isolated=1
  local t = {}
  if type(e) ~= "string" then return t end
  for pair in string.gmatch(e, "[^;]+") do
    local k, v = string.match(pair, "^([^=]+)=(.*)$")
    if k then t[k] = v end
  end
  return t
end

local function collect(kind, state_filter)
  local atoms = karmazyn.list_atoms(state_filter)
  local out = {}
  for i = 1, #atoms do
    local a = atoms[i]
    if a.S == kind then
      out[#out + 1] = a
    end
  end
  table.sort(out, function(x, y)
    return (x.get_T() or 0) > (y.get_T() or 0)
  end)
  return out
end

local function count_kind(kind)
  local atoms = karmazyn.list_atoms()
  local n = 0
  for i = 1, #atoms do
    if atoms[i].S == kind then n = n + 1 end
  end
  return n
end

local function bar_for(a)
  local tmax = karmazyn.T_MAX or 100
  local pct = (a.get_T_frac and a.get_T_frac() or ((a.get_T() or 0) / tmax)) * 100
  return karmazyn.ui.progress_bar(pct, 100, 14)
end

local meta = karmazyn.get_atom("starlink:meta")
local meta_t = meta and parse_meta_E(meta.E) or {}
local isolated = meta_t.isolated == "1"

local n_sat_view = count_kind("starlink:sat")
local n_cell_view = count_kind("starlink:cell")
-- katalog (prawda) z meta gdy isolate; inaczej widok = katalog
local n_sat = tonumber(meta_t.sats) or n_sat_view
local n_cell = tonumber(meta_t.cells) or n_cell_view
local n_hot_meta = tonumber(meta_t.hot)
local n_warm_meta = tonumber(meta_t.warm)

local cells_hot = collect("starlink:cell", "HOT")
local cells_warm = collect("starlink:cell", "WARM")
local sats_hot = collect("starlink:sat", "HOT")
local sats_warm = collect("starlink:sat", "WARM")

local bubbles = karmazyn.list_bubbles()
local bubble_names = {}
for i = 1, #bubbles do
  local b = bubbles[i]
  local lab = type(b) == "table" and (b.label or b.name or tostring(b)) or tostring(b)
  if type(lab) == "string" and (lab == "starlink" or lab == "sats" or lab == "grid" or lab:sub(1, 6) == "shell:") then
    bubble_names[#bubble_names + 1] = lab
  end
end
table.sort(bubble_names)

local mode = isolated and "ISOLATE (view Store)" or "shared Store"
local body = {
  string.format("mode=%s  epoch=%s  sys_T=%.2f",
    mode, tostring(karmazyn.get_epoch()), karmazyn.get_temperature()),
  string.format("catalog sat=%d cell=%d  |  view_atoms sat=%d cell=%d",
    n_sat, n_cell, n_sat_view, n_cell_view),
  string.format("cells HOT=%d WARM=%d | sats HOT=%d WARM=%d",
    n_hot_meta or #cells_hot, n_warm_meta or #cells_warm, #sats_hot, #sats_warm),
  string.format("prop=%s hot_only=%s",
    tostring(meta_t.prop or "?"), tostring(meta_t.hot_only or "?")),
  string.format("bubbles: %s", (#bubble_names > 0) and table.concat(bubble_names, ", ") or "(seed host first)"),
}

if n_sat == 0 and n_cell == 0 and not meta then
  body[#body + 1] = "--- empty ---"
  body[#body + 1] = "seed: python software/starlink_atoms.py --limit 400 --lua"
else
  body[#body + 1] = "--- top HOT cells (view) ---"
  local list = cells_hot
  if #list == 0 then list = cells_warm end
  local n = #list
  if n > 14 then n = 14 end
  if n == 0 then
    body[#body + 1] = "(none — run host refresh)"
  else
    for i = 1, n do
      local a = list[i]
      local e = tostring(a.E or "")
      if #e > 16 then e = e:sub(1, 16) end
      body[#body + 1] = string.format(
        "%-14s %s %5.1f %-5s %s",
        tostring(a.id), bar_for(a), a.get_T() or 0, tostring(a.state or "?"), e)
    end
    if #list > 14 then
      body[#body + 1] = string.format("… +%d more", #list - 14)
    end
  end
end

local res = karmazyn.get_resources()
body[#body + 1] = "--- get_resources (this Store only) ---"
body[#body + 1] = string.format("alive=%s HOT=%s WARM=%s COLD=%s bubbles=%s",
  tostring(res.alive or res.total or "?"),
  tostring(res.HOT or res.hot or "?"),
  tostring(res.WARM or "?"),
  tostring(res.COLD or "?"),
  tostring(res.bubbles or "?"))
if isolated then
  body[#body + 1] = string.format(
    "(catalog sat=%s stays on host Store — not mixed into get_resources)",
    tostring(n_sat))
end

print(karmazyn.ui.draw_frame("STARLINK · bubbles", body))
print("Faza3: multi-task = catalog Store + isolated Lua view Store")
