#!/usr/bin/env python3
"""Szybki przegląd stanu implementacji (bez pełnego unittest)."""
import os
import sys
import types

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
pkg = types.ModuleType("karmazyn_lua")
pkg.__path__ = [ROOT]
pkg.__file__ = os.path.join(ROOT, "__init__.py")
sys.modules["karmazyn_lua"] = pkg

from karmazyn_kernel import Store
from karmazyn_lua.lib import mount
import karmazyn_lua_math
import karmazyn_lua_table

print("=== CORE (math+table, bez string) ===")
ev = mount(Store(thermal=True), libs=[karmazyn_lua_math, karmazyn_lua_table])
checks = [
    ("arytmetyka", "return 1+2*3"),
    ("vararg #", "function f(...) return select('#', ...) end; return f(1,2,3)"),
    ("vararg fwd", "function g(a,...) return a, ... end; return g(10,20,30)"),
    ("long string", "return [[hello]]"),
    ("long nest", "return [==[a]]b]==]"),
    ("block comment", "--[[ x ]] return 42"),
    ("table sort", "t={3,1,2}; table.sort(t); return table.concat(t, ',')"),
    ("table pack", "local t=table.pack(1,2); return t.n"),
    ("math", "return math.floor(3.7)"),
    ("pcall", "return pcall(function() error('x') end)"),
    ("repeat?", "local i=0; repeat i=i+1 until i>=3; return i"),
    ("goto?", "goto L; ::L:: return 1"),
]
for name, code in checks:
    out = ev.eval_line(code)
    ok = not str(out).startswith("blad")
    print(f"  [{'OK' if ok else 'NO'}] {name:16s}  {out!r}"[:90])

print("\n=== string lib mount ===")
try:
    import karmazyn_lua_string
    mount(Store(thermal=True), libs=[karmazyn_lua_string])
    print("  [OK] mount string")
except Exception as e:
    print(f"  [NO] mount string: {type(e).__name__}: {e}")

print("\n=== default mount (wszystkie liby) ===")
try:
    mount(Store(thermal=True))
    print("  [OK] mount()")
except Exception as e:
    print(f"  [NO] mount(): {type(e).__name__}: {e}")

print("\n=== pliki ===")
for f in sorted(os.listdir(ROOT)):
    if f.endswith(".py") and not f.startswith("_"):
        path = os.path.join(ROOT, f)
        n = sum(1 for _ in open(path, encoding="utf-8"))
        print(f"  {n:5d}  {f}")
