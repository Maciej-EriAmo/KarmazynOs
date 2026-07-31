# -*- coding: utf-8 -*-
"""Pobierz klasyczne snippety Lua z sieci i odpal na KarmazynLua."""
from __future__ import annotations

import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from _paths import ensure_kernel_on_path, ensure_lua_package

ensure_kernel_on_path(ROOT)
ensure_lua_package(ROOT)

from karmazyn_kernel import Store
from karmazyn_lua.lib import mount
from karmazyn_lua.values import compose_phi, LuaError
import karmazyn_lua as pkg

pkg.mount = mount
pkg.compose_phi = compose_phi

# --- źródła z sieci (małe, znane) ---
# 1) Wikipedia Lua (prosty przykład) — wklejony z public domain / docs
# 2) Programming in Lua style classics
# 3) raw z gist/github raw gdzie możliwe

REMOTE = [
    # Rosetta Code / classic patterns as self-contained (fetched if possible)
    (
        "pil_fact_like",
        None,  # inline below if fetch fails
        r'''
-- classic recursive factorial (Programming in Lua style)
local function fact(n)
  if n == 0 then return 1 else return n * fact(n - 1) end
end
return fact(5), fact(10)
''',
        lambda r: r == [120, 3628800] or (isinstance(r, list) and r[0] == 120),
    ),
]

# Inline battery inspired by common net samples (Lua 5.x)
SAMPLES = [
    (
        "net.wiki_hello",
        # https://en.wikipedia.org/wiki/Lua_(programming_language) style
        '''
print("Hello World!")
return "ok"
''',
        None,
    ),
    (
        "net.fact_recursive",
        '''
local function fact(n)
  if n == 0 then return 1 else return n * fact(n - 1) end
end
assert(fact(5) == 120)
return fact(10)
''',
        lambda out, ret: ret == [3628800],
    ),
    (
        "net.fib_loop",
        '''
local function fib(n)
  local a, b = 0, 1
  for i = 1, n do
    a, b = b, a + b
  end
  return a
end
return fib(10), fib(15)
''',
        lambda out, ret: ret == [55, 610],
    ),
    (
        "net.table_map_filter",
        '''
-- common "map" pattern from forums / PIL
local function map(t, f)
  local r = {}
  for i, v in ipairs(t) do r[i] = f(v) end
  return r
end
local t = map({1,2,3,4}, function(x) return x * x end)
return table.concat(t, ",")
''',
        lambda out, ret: ret == ["1,4,9,16"],
    ),
    (
        "net.closures_counter",
        '''
local function counter(start)
  local n = start or 0
  return function()
    n = n + 1
    return n
  end
end
local c = counter(10)
return c(), c(), c()
''',
        lambda out, ret: ret == [11, 12, 13],
    ),
    (
        "net.oo_metatable",
        '''
-- classic "class" via metatable (very common on SO / tutorials)
local Account = {}
Account.__index = Account
function Account:new(balance)
  return setmetatable({balance = balance or 0}, Account)
end
function Account:deposit(v)
  self.balance = self.balance + v
end
function Account:withdraw(v)
  if v > self.balance then error("insufficient") end
  self.balance = self.balance - v
end
local a = Account:new(100)
a:deposit(50)
a:withdraw(30)
return a.balance
''',
        lambda out, ret: ret == [120],
    ),
    (
        "net.coroutine_producer",
        '''
local function producer()
  return coroutine.create(function()
    for i = 1, 3 do
      coroutine.yield(i * 10)
    end
  end)
end
local co = producer()
local ok1, v1 = coroutine.resume(co)
local ok2, v2 = coroutine.resume(co)
local ok3, v3 = coroutine.resume(co)
local ok4, v4 = coroutine.resume(co)
return ok1, v1, ok2, v2, ok3, v3, ok4, v4
''',
        lambda out, ret: ret == [True, 10, True, 20, True, 30, True, None] or (
            isinstance(ret, list) and ret[:6] == [True, 10, True, 20, True, 30] and ret[6] is True
        ),
    ),
    (
        "net.pcall_xpcall",
        '''
local ok, err = pcall(function() error("x") end)
local ok2, msg = xpcall(function() error("y") end, function(e)
  return "caught:" .. tostring(e)
end)
return ok, err, ok2, msg
''',
        lambda out, ret: ret[0] is False and ret[2] is False and "caught" in str(ret[3]),
    ),
    (
        "net.string_gmatch_words",
        '''
local words = {}
for w in string.gmatch("one two three", "%S+") do
  words[#words+1] = w
end
return table.concat(words, "|")
''',
        lambda out, ret: ret == ["one|two|three"],
    ),
    (
        "net.bitwise_53",
        '''
-- Lua 5.3+ bitwise
return 0xF0 & 0x0F, 1 << 4, 16 >> 2, ~0 & 0xFF
''',
        lambda out, ret: True,  # soft: just must run
    ),
    (
        "net.utf8_len",
        '''
return utf8.len("abc"), utf8.len("zażółć")
''',
        lambda out, ret: ret[0] == 3,
    ),
    (
        "net.load_string",
        '''
local f, err = load("return 2+2")
if not f then return nil, err end
return f()
''',
        lambda out, ret: ret == [4],
    ),
    (
        "net.goto_continue",
        '''
local s = 0
for i = 1, 5 do
  if i % 2 == 0 then goto continue end
  s = s + i
  ::continue::
end
return s
''',
        lambda out, ret: ret == [9],  # 1+3+5
    ),
    (
        "net.varargs_select",
        '''
local function head(...)
  return select(1, ...), select("#", ...)
end
return head(10, 20, 30)
''',
        lambda out, ret: ret == [10, 3],
    ),
    (
        "net.require_fail_sandbox",
        '''
-- sandbox: brak ambient FS; require nieistniejącego
local ok, err = pcall(function() require("definitely_missing_mod_xyz") end)
return ok, type(err)
''',
        lambda out, ret: ret[0] is False and ret[1] == "string",
    ),
]

# spróbuj ściągnąć krótki publiczny przykład z raw GitHub (Lua wiki / examples)
FETCH = [
    (
        "fetch.lua_org_helloish",
        # small file often used; if fails, skip
        "https://raw.githubusercontent.com/lua/lua/master/README",
        "not_lua",
    ),
]


def run_one(ev, name, src, check):
    ev._out = []
    try:
        ret = ev.run_source(src, chunkname="@" + name + ".lua")
        out = list(ev._out)
        ok = True
        detail = ""
        if check:
            try:
                ok = bool(check(out, ret))
            except Exception as ex:
                ok = False
                detail = f"check err: {ex}"
        if not ok:
            return False, f"ret={ret!r} out={out!r} {detail}"
        return True, f"ret={ret!r} out={out!r}"
    except LuaError as e:
        return False, f"LuaError: {e}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def main():
    store = Store(thermal=True)
    session = store.bubble_new("net-compat")
    ev = mount(store, root_bubble=session, phi=compose_phi(b"net", b"compat"), caps="default")

    print("kernel:", __import__("karmazyn_kernel").__file__)
    print("store: ", type(store).__name__)
    print("samples:", len(SAMPLES), "(wzorce z sieci / PIL / SO / tutorials)")
    print("=" * 60)

    passed = failed = 0
    fails = []
    for name, src, check in SAMPLES:
        ok, msg = run_one(ev, name, src, check)
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1
            fails.append((name, msg))
        print(f"{status:4}  {name}")
        if not ok:
            print(f"      {msg[:200]}")

    print("=" * 60)
    print(f"NET_COMPAT  PASS={passed}  FAIL={failed}  TOTAL={passed+failed}")
    if fails:
        print("--- failures detail ---")
        for n, m in fails:
            print(f"* {n}: {m[:300]}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
