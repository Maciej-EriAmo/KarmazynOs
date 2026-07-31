--[[
  memviz.lua — aktywna pamięć substratu: tworzenie → zakres T/reach → usuwanie
  ==========================================================================
  Wymaga host API `karmazyn.*` (boot / memviz_run.py).

  Pokazuje:
    1) snapshot zasobów Store (stats)
    2) tworzenie atomów (ciepłe / zimne / do consolidate)
    3) listę z paskami T i stanem HOT|WARM|COLD|TOMB
    4) step/settle — orphan bez reach ginie; skonsolidowany zostaje
    5) delete_atom + ponowny snapshot

  Uruchom:
    python memviz_run.py          (z katalogu LUA)
    karmazyn> :tool memviz        (boot)
]]

local function lines_of(...)
  local t = {}
  for i = 1, select("#", ...) do
    t[i] = select(i, ...)
  end
  return t
end

local function res_line(res, key)
  local v = res[key]
  if v == nil then return key .. ": ?" end
  return string.format("%-14s %s", key .. ":", tostring(v))
end

local function snapshot(title)
  local res = karmazyn.get_resources()
  local atoms = karmazyn.list_atoms()
  local tmax = karmazyn.T_MAX or 100
  local body = {
    string.format("epoch=%s  temp_sys=%.3f  atoms=%d",
      tostring(karmazyn.get_epoch()),
      karmazyn.get_temperature(),
      #atoms),
    string.format("T_scale: TOMB=%.0f  WARM=%.0f  HOT=%.0f  MAX=%.0f  INIT=%.0f",
      karmazyn.T_TOMB or 2, karmazyn.T_WARM or 30,
      karmazyn.T_HOT or 70, tmax, karmazyn.T_INIT or 50),
    "--- store.stats ---",
    res_line(res, "total"),
    res_line(res, "alive"),
    res_line(res, "HOT"),
    res_line(res, "WARM"),
    res_line(res, "COLD"),
    res_line(res, "TOMB"),
    res_line(res, "reaped"),
    res_line(res, "retained_tomb"),
    res_line(res, "bubbles"),
    "--- atomy ---",
  }
  if #atoms == 0 then
    table.insert(body, "(brak)")
  else
    local limit = 24
    local nshow = #atoms
    if nshow > limit then nshow = limit end
    for i = 1, nshow do
      local a = atoms[i]
      local pct = (a.get_T_frac and a.get_T_frac() or (a.get_T() / tmax)) * 100
      local bar = karmazyn.ui.progress_bar(pct, 100, 16)
      local e = tostring(a.E)
      if #e > 16 then e = e:sub(1, 16) end
      local s = tostring(a.S)
      if #s > 12 then s = s:sub(1, 12) end
      table.insert(body, string.format(
        "%-10s %s %5.1f%% %-5s  S=%s E=%s",
        a.id, bar, pct, a.state or "?", s, e))
    end
    if #atoms > limit then
      table.insert(body, string.format("… +%d więcej", #atoms - limit))
    end
  end
  print(karmazyn.ui.draw_frame(title, body))
end

local function layer_bar()
  -- mini mapa warstw FSM
  local hot = #karmazyn.list_atoms("HOT")
  local warm = #karmazyn.list_atoms("WARM")
  local cold = #karmazyn.list_atoms("COLD")
  local tomb = #karmazyn.list_atoms("TOMB")
  local total = math.max(1, hot + warm + cold + tomb)
  local w = 28
  local function seg(n, ch)
    local k = math.floor((n / total) * w + 0.5)
    if n > 0 and k < 1 then k = 1 end
    return string.rep(ch, k)
  end
  local s = seg(hot, "H") .. seg(warm, "W") .. seg(cold, "C") .. seg(tomb, "T")
  if #s < w then s = s .. string.rep(".", w - #s) end
  if #s > w then s = s:sub(1, w) end
  print(karmazyn.ui.draw_frame("WARSTWY (H/W/C/T)", lines_of(
    "[" .. s .. "]",
    string.format("HOT=%d WARM=%d COLD=%d TOMB=%d", hot, warm, cold, tomb)
  )))
end

------------------------------------------------------------
-- 0. prolog
------------------------------------------------------------
print("")
print("MEMVIZ — cykl życia atomu na substracie Karmazyn (kernel 1.1 / host 1.0)")
print("prawo: temperatura = KIEDY, osiągalność = CZY")
print("")

snapshot("0. START (pusta sesja gościa + lib)")

------------------------------------------------------------
-- 1. tworzenie atomów w różnych zakresach T
------------------------------------------------------------
-- T bezwzględne (skala jądra 0..T_MAX) — bez fałszywych ułamków 0..1
local specs = {
  { id = "alpha", S = "signal", E = "cieplo-init",  T = 80 },
  { id = "beta",  S = "signal", E = "goracy-HOT",   T = karmazyn.T_HOT or 70 },
  { id = "gamma", S = "noise",  E = "chlodny-low",  T = 5 },
  { id = "delta", S = "keep",   E = "do-korzenia",  T = karmazyn.T_INIT or 50 },
}

local created = {}
for i = 1, #specs do
  local sp = specs[i]
  local a = karmazyn.create_atom(sp.id, sp.S, sp.E, sp.T)
  if type(a) == "table" then
    created[#created + 1] = a.id
  else
    print("! create " .. sp.id .. ": " .. tostring(a))
  end
end

snapshot("1. PO CREATE (" .. #created .. " atomów)")
layer_bar()

------------------------------------------------------------
-- 2. zakres pracy: refresh / set_state / odczyt
------------------------------------------------------------
local a = karmazyn.get_atom("alpha")
if a then
  a.refresh()
  a.set_E("po-refresh")
end
local b = karmazyn.get_atom("gamma")
if b then
  b.set_state("WARM")
end

snapshot("2. PO REFRESH + set_state(gamma→WARM)")

------------------------------------------------------------
-- 3. consolidate delta → bąbel-korzeń (reach)
------------------------------------------------------------
local bub = karmazyn.consolidate("delta")
print(karmazyn.ui.draw_frame("3. CONSOLIDATE delta", lines_of(
  "bubble = " .. tostring(bub),
  "delta ma root reach — settle nie powinien go zabić",
  "alpha/beta/gamma bez korzenia → kandydaci do vacuum gdy zimne"
)))

------------------------------------------------------------
-- 4. step / settle — ciśnienie GC (T = KIEDY, reach = CZY)
------------------------------------------------------------
-- najpierw naturalny decay (widać schładzanie warstw)
local nstep = 8
karmazyn.step(nstep)
snapshot("4a. PO step(" .. nstep .. ") — decay T")
layer_bar()

-- potem spychamy orphanów do TOMB: bez reach → vacuum; delta ma root
for _, id in ipairs({ "alpha", "beta", "gamma" }) do
  local x = karmazyn.get_atom(id)
  if x then x.set_state("TOMB") end
end
-- delta też zimna, ale skonsolidowana → retained / żywa
local dkeep = karmazyn.get_atom("delta")
if dkeep then dkeep.set_state("COLD") end

karmazyn.step(4)
snapshot("4b. PO TOMB(orphans)+step — vacuum")
layer_bar()

local still = {}
for i = 1, #created do
  local id = created[i]
  if karmazyn.get_atom(id) ~= nil then
    still[#still + 1] = id
  end
end
local still_s = (#still > 0) and table.concat(still, ", ") or "(nikt)"
local res = karmazyn.get_resources()
print(karmazyn.ui.draw_frame("REACH CHECK", lines_of(
  "żywe po vacuum: " .. still_s,
  "delta ma consolidate/root → powinna przeżyć",
  "alpha/beta/gamma: TOMB + brak reach → reaped",
  "reaped=" .. tostring(res.reaped) .. "  retained_tomb=" .. tostring(res.retained_tomb)
)))

------------------------------------------------------------
-- 5. jawne usuwanie + klon
------------------------------------------------------------
if karmazyn.get_atom("delta") then
  local clone = karmazyn.clone_atom("delta", "delta_copy")
  print("clone delta → delta_copy: " .. (type(clone) == "table" and clone.id or tostring(clone)))
end

local del_ok = karmazyn.delete_atom("delta")
local del_copy = karmazyn.delete_atom("delta_copy")
-- sprzątanie resztek jeśli żyją
for _, id in ipairs({ "alpha", "beta", "gamma" }) do
  if karmazyn.get_atom(id) then
    karmazyn.delete_atom(id)
  end
end

snapshot("5. PO DELETE (delta, kopie, resztki)")
layer_bar()

print(karmazyn.ui.draw_frame("MEMVIZ DONE", lines_of(
  "create_atom  → alokacja w Store",
  "T / state    → zakres termiczny (KIEDY)",
  "consolidate  → reach (CZY wolno żyć)",
  "step/settle  → vacuum nieosiągalnych",
  "delete_atom  → jawne usunięcie",
  "",
  "host API " .. tostring(karmazyn._VERSION) .. "  |  T_MAX=" .. tostring(karmazyn.T_MAX)
)))
print("")
