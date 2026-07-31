# -*- coding: utf-8 -*-
"""Ściągnij prawdziwe pliki .lua z sieci i uruchom na KarmazynLua."""
from __future__ import annotations
import os, sys, re, urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from _paths import ensure_kernel_on_path, ensure_lua_package
ensure_kernel_on_path(ROOT); ensure_lua_package(ROOT)
from karmazyn_kernel import Store
from karmazyn_lua.lib import mount
from karmazyn_lua.values import compose_phi, LuaError
import karmazyn_lua as pkg
pkg.mount = mount; pkg.compose_phi = compose_phi

# małe, samodzielne pliki (bez C modules / FS)
URLS = [
    # classic single-file demos
    ("https://raw.githubusercontent.com/rxi/json.lua/master/json.lua", "lib"),  # library, need exercise
    ("https://raw.githubusercontent.com/kikito/inspect.lua/master/inspect.lua", "lib"),
]

# małe chunki "z sieci" jako self-tests bibliotek po fetch
def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "KarmazynLua-compat/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")

def mount_ev():
    store = Store(thermal=True)
    return mount(store, root_bubble=store.bubble_new("fetch"), phi=compose_phi(b"f", b"c"), caps="default")

def main():
    print("Fetching real Lua sources from GitHub raw…")
    results = []

    # 1) json.lua (rxi) — bardzo popularny pure-Lua
    try:
        src = fetch("https://raw.githubusercontent.com/rxi/json.lua/master/json.lua")
        print(f"  json.lua  bytes={len(src)}")
        ev = mount_ev()
        # załaduj jako chunk zwracający moduł (json.lua ends with return json)
        # plik to library: load + call
        wrapped = src + "\n" + r'''
-- exercise
local j = ...
if type(j) ~= "table" then
  -- some versions return module; if chunk returns json at end, run_source gets it
end
'''
        # compile as function that returns module
        fn = ev.compile_chunk(src, chunkname="@json.lua")
        mod = ev._call(fn, [])
        if not mod:
            raise RuntimeError("json chunk returned empty")
        json = mod[0]
        # inject as global for test chunk
        # use run_source with preload
        ev.register_preload("json", src, chunkname="@json.lua")
        ret = ev.run_source(r'''
local json = require("json")
local t = {a=1, b={2,3}, s="hi"}
local enc = json.encode(t)
local dec = json.decode(enc)
assert(dec.a == 1)
assert(dec.b[1] == 2)
assert(dec.s == "hi")
local arr = json.decode("[1,2,3]")
assert(arr[1]+arr[2]+arr[3] == 6)
return enc, #arr
''', chunkname="@json_test.lua")
        print("  PASS  rxi/json.lua  ->", ret)
        results.append(("rxi/json.lua", True, str(ret)))
    except Exception as e:
        print("  FAIL  rxi/json.lua  ->", type(e).__name__, e)
        results.append(("rxi/json.lua", False, f"{type(e).__name__}: {e}"))

    # 2) inspect.lua (kikito)
    try:
        src = fetch("https://raw.githubusercontent.com/kikito/inspect.lua/master/inspect.lua")
        print(f"  inspect.lua  bytes={len(src)}")
        ev = mount_ev()
        ev.register_preload("inspect", src, chunkname="@inspect.lua")
        ret = ev.run_source(r'''
local inspect = require("inspect")
local s = inspect({x=1, y={2,3}})
assert(type(s) == "string")
assert(string.find(s, "x", 1, true))
return #s > 5
''', chunkname="@inspect_test.lua")
        print("  PASS  kikito/inspect.lua  ->", ret)
        results.append(("kikito/inspect.lua", True, str(ret)))
    except Exception as e:
        print("  FAIL  kikito/inspect.lua  ->", type(e).__name__, e)
        results.append(("kikito/inspect.lua", False, f"{type(e).__name__}: {e}"))

    # 3) mały algorytm z Rosetta-style (binary search) — inline bo RC to wiki HTML
    try:
        ev = mount_ev()
        ret = ev.run_source(r'''
-- Rosetta Code style binary search (Lua)
local function bsearch(t, x)
  local lo, hi = 1, #t
  while lo <= hi do
    local mid = (lo + hi) // 2
    if t[mid] == x then return mid
    elseif t[mid] < x then lo = mid + 1
    else hi = mid - 1 end
  end
  return nil
end
local t = {1,3,5,7,9,11}
return bsearch(t, 7), bsearch(t, 2) == nil
''', chunkname="@bsearch.lua")
        assert ret == [4, True], ret
        print("  PASS  rosetta_bsearch  ->", ret)
        results.append(("rosetta_bsearch", True, str(ret)))
    except Exception as e:
        print("  FAIL  rosetta_bsearch  ->", e)
        results.append(("rosetta_bsearch", False, str(e)))

    # 4) penlight-like path split pure snippet common online
    try:
        ev = mount_ev()
        ret = ev.run_source(r'''
local function split(s, sep)
  local r = {}
  local pat = "([^" .. sep .. "]+)"
  for part in string.gmatch(s, pat) do r[#r+1] = part end
  return r
end
local p = split("a/b/c", "/")
return table.concat(p, ".")
''', chunkname="@split.lua")
        assert ret == ["a.b.c"], ret
        print("  PASS  net_string_split  ->", ret)
        results.append(("net_string_split", True, str(ret)))
    except Exception as e:
        print("  FAIL  net_string_split  ->", e)
        results.append(("net_string_split", False, str(e)))

    p = sum(1 for _,ok,_ in results if ok)
    f = sum(1 for _,ok,_ in results if not ok)
    print("=" * 50)
    print(f"FETCH_COMPAT  PASS={p} FAIL={f}")
    for name, ok, msg in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}  {msg[:120]}")
    return 0 if f == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
