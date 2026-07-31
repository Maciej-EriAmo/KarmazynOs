--[[
  kombajn.lua — bateria testów poprawności KarmazynLua (gość na substracie)
  ==========================================================================
  Uruchom:  python kombajn_run.py
  Albo wklej do eval_line (runner ładuje cały plik).

  Konwencja: każdy test woła check(nazwa, warunek) lub check_eq(nazwa, a, b).
  Na końcu: PASS / FAIL + liczby. exit code runnera = 0 gdy FAIL==0.
]]

local pass, fail = 0, 0
local errors = {}

local function check(name, cond)
  if cond then
    pass = pass + 1
  else
    fail = fail + 1
    errors[#errors + 1] = name
  end
end

local function check_eq(name, a, b)
  check(name, a == b)
end

local function check_type(name, v, t)
  check(name, type(v) == t)
end

------------------------------------------------------------
-- 1. Arytmetyka i typy
------------------------------------------------------------
check_eq("arith.prec", 1 + 2 * 3, 7)
check_eq("arith.pow", 2 ^ 3 ^ 2, 512.0)
check_eq("arith.idiv", 7 // 2, 3)
check_eq("arith.mod", 10 % 3, 1)
check_eq("type.num", type(1), "number")
check_eq("type.str", type("a"), "string")
check_eq("type.bool", type(true), "boolean")
check_eq("type.nil", type(nil), "nil")
check_eq("type.table", type({}), "table")
check_eq("type.fn", type(function() end), "function")

------------------------------------------------------------
-- 2. Stringi i konkatenacja
------------------------------------------------------------
check_eq("str.cat", "a" .. "b" .. 1, "ab1")
check_eq("str.len", #"magos", 5)
check_eq("str.sub", string.sub("abcdef", 2, 4), "bcd")
check_eq("str.upper", string.upper("Ab"), "AB")
check_eq("str.method", ("hi"):upper(), "HI")

------------------------------------------------------------
-- 3. Wzorce Lua (%b, %f, captures)
------------------------------------------------------------
check_eq("pat.digits", string.match("xy123z", "%d+"), "123")
check_eq("pat.bal", string.match("a(b(c)d)e", "%b()"), "(b(c)d)")
check_eq("pat.front", string.match(" the", "%f[%w]the"), "the")
local cx, cy = string.match("ab12", "(%a+)(%d+)")
check_eq("pat.cap", cx .. cy, "ab12")
local _, nsub = string.gsub("a1b2", "%d", "X")
check_eq("pat.gsub", nsub, 2)

------------------------------------------------------------
-- 4. Tabele
------------------------------------------------------------
local t = {10, 20, 30, name = "k"}
check_eq("tab.arr", t[2], 20)
check_eq("tab.hash", t.name, "k")
check_eq("tab.len", #t, 3)
table.insert(t, 2, 15)
check_eq("tab.insert", table.concat(t, ","), "10,15,20,30")
table.remove(t, 2)
check_eq("tab.remove", #t, 3)
local a = {1, 2, 3, 4}
table.move(a, 2, 4, 1)
check_eq("tab.move", table.concat(a, ","), "2,3,4,4")
local p = table.pack(7, 8)
check_eq("tab.pack", p.n + p[1], 9)

------------------------------------------------------------
-- 5. Sterowanie
------------------------------------------------------------
local s = 0
for i = 1, 5 do s = s + i end
check_eq("for.num", s, 15)
local r = 0
repeat r = r + 1 until r >= 3
check_eq("repeat", r, 3)
local w = 0
while w < 4 do w = w + 1 end
check_eq("while", w, 4)
local g = ""
for i = 1, 4 do
  if i % 2 == 0 then goto cont end
  g = g .. i
  ::cont::
end
check_eq("goto.cont", g, "13")

------------------------------------------------------------
-- 6. Funkcje, multi-return, varargi
------------------------------------------------------------
local function pair() return 1, 2 end
local x, y = pair()
check_eq("multi.assign", x + y, 3)
local function va(...) return select("#", ...) end
check_eq("vararg.count", va(1, 2, 3, 4), 4)
local function fwd(...) return select(1, ...) end
check_eq("vararg.fwd", fwd(9, 8), 9)

------------------------------------------------------------
-- 7. Metatabele
------------------------------------------------------------
local o = {}
local mt = {__index = {z = 99}, __add = function(a, b) return 100 end}
setmetatable(o, mt)
check_eq("meta.index", o.z, 99)
check_eq("meta.add", (setmetatable({}, mt) + 1), 100)

------------------------------------------------------------
-- 8. _ENV / _G / _VERSION
------------------------------------------------------------
check_eq("ver", _VERSION, "Lua 5.5")
check_eq("G.type", type(_G), "table")
check_eq("G.ver", _G._VERSION, "Lua 5.5")
check_eq("ENV", type(_ENV), "table")
_ENV.kombajn_mark = 7
check_eq("ENV.write", kombajn_mark, 7)

------------------------------------------------------------
-- 9. const / close / global
------------------------------------------------------------
local const_ok = true
local okc, _ = pcall(function()
  local <const> c = 1
  c = 2
end)
check("const.block", not okc)
local closed = 0
do
  local x <close> = setmetatable({}, {
    __close = function() closed = closed + 1 end
  })
end
check_eq("close.fire", closed, 1)
global kombajn_g = 11
check_eq("global.set", kombajn_g, 11)

------------------------------------------------------------
-- 10. pcall / error
------------------------------------------------------------
local ok1 = pcall(function() return 1 end)
check("pcall.ok", ok1 == true)
local ok2, err = pcall(function() error("boom") end)
check("pcall.err", ok2 == false and err == "boom")

------------------------------------------------------------
-- 11. load / require
------------------------------------------------------------
local f = load("return 40+2")
check_eq("load.run", f(), 42)
local bad, emsg = load("!!!")
check("load.fail", bad == nil and type(emsg) == "string")
package.preload.kombajn_mod = function() return {ok = true} end
check("require", require("kombajn_mod").ok == true)
check("require.cache", require("kombajn_mod").ok == true)

------------------------------------------------------------
-- 12. coroutine
------------------------------------------------------------
local co = coroutine.create(function()
  coroutine.yield(10)
  coroutine.yield(20)
  return 30
end)
local o1, v1 = coroutine.resume(co)
local o2, v2 = coroutine.resume(co)
local o3, v3 = coroutine.resume(co)
check("co1", o1 == true and v1 == 10)
check("co2", o2 == true and v2 == 20)
check("co3", o3 == true and v3 == 30)
check_eq("co.dead", coroutine.status(co), "dead")

------------------------------------------------------------
-- 13. math / os / utf8 / pack
------------------------------------------------------------
check_eq("math.floor", math.floor(3.7), 3)
check_eq("math.type", math.type(3), "integer")
check_eq("os.time.type", type(os.time()), "number")
check_eq("utf8.char", utf8.char(65, 66), "AB")
check_eq("utf8.len", utf8.len("abc"), 3)
check_eq("pack.size", string.packsize(">I4"), 4)
local packed = string.pack(">I2", 258)
local uv = string.unpack(">I2", packed)
check_eq("pack.round", uv, 258)

------------------------------------------------------------
-- 14. long string / komentarz blokowy (składnia już w tym pliku)
------------------------------------------------------------
local ls = [[line]]
check_eq("long.str", ls, "line")

------------------------------------------------------------
-- 15. format / io / collectgarbage
------------------------------------------------------------
check_eq("fmt.pad", string.format("%05d", 7), "00007")
check_eq("fmt.f", string.format("%.2f", 3.14159), "3.14")
check_eq("io.type", type(io.write), "function")
check_eq("cg.type", type(collectgarbage), "function")
collectgarbage("collect")
check("cg.run", true)
-- po GC locale chunka muszą żyć (extra_reach ramek wywołań)
check_eq("cg.alive", type(check), "function")

------------------------------------------------------------
-- 16. goto scope (już w parserze — legalny continue)
------------------------------------------------------------
local gs = 0
for i = 1, 2 do
  goto skip
  gs = gs + 100
  ::skip::
  gs = gs + 1
end
check_eq("goto.skip", gs, 2)

------------------------------------------------------------
-- 17. Faza 1: traceback / searchers / load name
------------------------------------------------------------
check_eq("dbg.type", type(debug.traceback), "function")
local tb = debug.traceback("MSG", 1)
check("dbg.has_msg", type(tb) == "string" and string.find(tb, "MSG", 1, true) ~= nil)
check("dbg.has_stack", string.find(tb, "stack traceback", 1, true) ~= nil)
local ok_e, err_e = pcall(function() error("E1") end)
check("err.pcall", ok_e == false and err_e == "E1")
local ok_x, err_x = xpcall(function() error("E2") end, function(e)
  return debug.traceback(e, 2)
end)
check("err.xpcall_tb", ok_x == false and type(err_x) == "string"
  and string.find(err_x, "stack traceback", 1, true) ~= nil)
check_eq("searchers.type", type(package.searchers[1]), "function")
local f_named, e_named = load("return 2+2", "chunk_kombajn")
check_eq("load.named", f_named and f_named() or nil, 4)
local fb, eb = load("???", "badchunk")
check("load.errname", fb == nil and type(eb) == "string" and string.find(eb, "badchunk", 1, true) ~= nil)
package.preload.kombajn_s2 = function(name)
  return { from = name }
end
check_eq("require.searcher", require("kombajn_s2").from, "kombajn_s2")

------------------------------------------------------------
-- 18. Faza A/B/C: debug.* / coro close / dump forbid / cg.step
------------------------------------------------------------
check_eq("dbg.getinfo.type", type(debug.getinfo), "function")
check_eq("dbg.getlocal.type", type(debug.getlocal), "function")
check_eq("dbg.getupvalue.type", type(debug.getupvalue), "function")
local function _gi_probe()
  local info = debug.getinfo(1, "nS")
  return type(info) == "table" and type(info.name) == "string"
    and type(info.source) == "string" and info.what ~= nil
end
check("dbg.getinfo.fields", _gi_probe())
local function _gl_probe(a)
  local n, v = debug.getlocal(1, 1)
  return n == "a" and v == 77
end
check("dbg.getlocal.param", _gl_probe(77))
local function _sl_probe()
  local x = 1
  debug.setlocal(1, 1, 9)
  return x == 9
end
check("dbg.setlocal", _sl_probe())
-- upvalues = wiązania env domknięcia (wiele lokalnych chunka) — szukamy wartości 3
local _uv = 3
local function _gu_probe()
  return _uv
end
local gu_ok = false
for i = 1, 64 do
  local un, uv = debug.getupvalue(_gu_probe, i)
  if un == nil then break end
  if uv == 3 then gu_ok = true; break end
end
check("dbg.getupvalue", gu_ok)
check_eq("co.isyieldable.type", type(coroutine.isyieldable), "function")
check("co.isyieldable.main", coroutine.isyieldable() == false)
local co_c = coroutine.create(function()
  return coroutine.isyieldable()
end)
local ok_c, iy = coroutine.resume(co_c)
check("co.isyieldable.in", ok_c == true and iy == true)
local co_cl = coroutine.create(function()
  coroutine.yield(1)
  return 2
end)
coroutine.resume(co_cl)
local ok_close = coroutine.close(co_cl)
check("co.close", ok_close == true)
check("co.close.status", coroutine.status(co_cl) == "dead")
local ok_rs = coroutine.resume(co_cl)
check("co.close.dead", ok_rs == false)
check("cg.step", collectgarbage("step", 1) == true)
local ok_dump, err_dump = pcall(function()
  return string.dump(function() end)
end)
check("str.dump.forbid", ok_dump == false and type(err_dump) == "string")

------------------------------------------------------------
-- 19. weak / __gc (produkcja 1.1)
-- (locale na scope chunka / funkcji — nie zagnieżdżony do…end po GC)
------------------------------------------------------------
local weak_holder = {}
setmetatable(weak_holder, { __mode = "v" })
local function _weak_drop()
  local payload = { n = 1 }
  weak_holder.k = payload
end
_weak_drop()
collectgarbage("collect")
check("weak.v", weak_holder.k == nil)

local gc_n = 0
local function _gc_drop()
  local t = {}
  setmetatable(t, { __gc = function() gc_n = gc_n + 1 end })
end
_gc_drop()
collectgarbage("collect")
check("gc.finalizer", gc_n >= 1)

------------------------------------------------------------
-- 20. P0: nested block + GC (1.1.1)
------------------------------------------------------------
do
  local nest_x = 42
  collectgarbage("collect")
  check_eq("p0.nested_do", nest_x, 42)
end
local nest_s = 0
for i = 1, 2 do
  local k = i * 10
  collectgarbage("collect")
  nest_s = nest_s + k
end
check_eq("p0.nested_for", nest_s, 30)

------------------------------------------------------------
-- Raport
------------------------------------------------------------
print("========== KOMBAJN KarmazynLua ==========")
print("PASS: " .. pass)
print("FAIL: " .. fail)
if fail > 0 then
  print("Failed tests:")
  for i = 1, #errors do
    print("  - " .. errors[i])
  end
end
print("TOTAL: " .. (pass + fail))
print("=========================================")
-- marker dla runnera Pythona:
print("KOMBAJN_RESULT " .. pass .. " " .. fail)
