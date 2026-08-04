--[[
  starlink_hot.lua — HOT/WARM cells (Faza 3 isolate-aware)
  ========================================================
  Host isolate:
    python software/starlink_atoms.py --limit 400 --hot-only --lua-hot
]]

local function parse_meta_E(e)
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
    if atoms[i].S == kind then out[#out + 1] = atoms[i] end
  end
  table.sort(out, function(x, y)
    return (x.get_T() or 0) > (y.get_T() or 0)
  end)
  return out
end

local function bar_for(a)
  local tmax = karmazyn.T_MAX or 100
  local pct = (a.get_T_frac and a.get_T_frac() or ((a.get_T() or 0) / tmax)) * 100
  return karmazyn.ui.progress_bar(pct, 100, 14)
end

local meta = karmazyn.get_atom("starlink:meta")
local mt = meta and parse_meta_E(meta.E) or {}
local cells_hot = collect("starlink:cell", "HOT")
local cells_warm = collect("starlink:cell", "WARM")
local sats_hot = collect("starlink:sat", "HOT")
local sats_warm = collect("starlink:sat", "WARM")

local body = {
  string.format("epoch=%s  isolated=%s  catalog_sat=%s catalog_cell=%s",
    tostring(karmazyn.get_epoch()),
    tostring(mt.isolated or "0"),
    tostring(mt.sats or "?"),
    tostring(mt.cells or "?")),
  string.format("view cells HOT=%d WARM=%d | sats HOT=%d WARM=%d",
    #cells_hot, #cells_warm, #sats_hot, #sats_warm),
  "--- top cells (HOT then WARM) ---",
}

local function dump_list(list, limit)
  local n = #list
  if n > limit then n = limit end
  for i = 1, n do
    local a = list[i]
    local e = tostring(a.E or "")
    if #e > 18 then e = e:sub(1, 18) end
    body[#body + 1] = string.format(
      "%-14s %s %5.1f %-5s E=%s",
      tostring(a.id), bar_for(a), a.get_T() or 0, tostring(a.state or "?"), e)
  end
  if #list > limit then
    body[#body + 1] = string.format("… +%d more", #list - limit)
  end
  if #list == 0 then body[#body + 1] = "(none)" end
end

dump_list(cells_hot, 12)
if #cells_hot < 8 then
  body[#body + 1] = "--- warm cells ---"
  dump_list(cells_warm, 8)
end

local res = karmazyn.get_resources()
body[#body + 1] = "--- get_resources (view Store) ---"
body[#body + 1] = string.format("alive=%s HOT=%s WARM=%s bubbles=%s",
  tostring(res.alive or res.total or "?"),
  tostring(res.HOT or res.hot or "?"),
  tostring(res.WARM or "?"),
  tostring(res.bubbles or "?"))

print(karmazyn.ui.draw_frame("STARLINK HOT (isolated view)", body))
