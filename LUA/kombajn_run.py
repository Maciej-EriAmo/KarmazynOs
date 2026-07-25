#!/usr/bin/env python3
"""Uruchom kombajn.lua na KarmazynLua + Kernel Karmazyn.

  python kombajn_run.py
  exit 0  → FAIL==0
  exit 1  → są błędy / FAIL>0
"""
from __future__ import annotations

import os
import re
import sys
import types

ROOT = os.path.dirname(os.path.abspath(__file__))
KERNEL = os.path.normpath(os.path.join(ROOT, "..", "Kernel Karmazyn"))
if not os.path.isdir(KERNEL):
    KERNEL = r"C:\Users\drwis\Kernel Karmazyn"

if os.path.isdir(KERNEL):
    sys.path.insert(0, KERNEL)
sys.path.insert(0, ROOT)

pkg = types.ModuleType("karmazyn_lua")
pkg.__path__ = [ROOT]
pkg.__file__ = os.path.join(ROOT, "__init__.py")
sys.modules["karmazyn_lua"] = pkg

from karmazyn_kernel import Store  # noqa: E402
from karmazyn_lua.lib import mount  # noqa: E402
from karmazyn_lua.values import compose_phi  # noqa: E402

pkg.mount = mount
pkg.compose_phi = compose_phi


def main() -> int:
    path = os.path.join(ROOT, "kombajn.lua")
    with open(path, encoding="utf-8") as f:
        src = f.read()

    store = Store(thermal=True)
    session = store.bubble_new("kombajn-session")
    phi = compose_phi(b"kombajn", b"test")
    ev = mount(store, root_bubble=session, phi=phi, caps="default")

    print(f"kernel: {__import__('karmazyn_kernel').__file__}")
    print(f"phi:    {phi!r}")
    print(f"source: {path} ({len(src)} bajtów)")
    print("---")

    # cały plik jako jeden chunk (parser → funkcja → call); bez load-z-pliku
    from karmazyn_lua.lexer import tokenize
    from karmazyn_lua.parser import Parser
    from karmazyn_lua.values import LuaFunction, LuaError

    try:
        block = Parser(tokenize(src)).parse_chunk()
    except LuaError as e:
        print("PARSE ERROR:", e)
        return 1

    wrap = store.bubble_new("kombajn-chunk")
    ea = store.atom_new("var", "_ENV", value=ev.G)
    wrap.bind("_ENV", ea)
    fn = LuaFunction(["..."], block, wrap, name="kombajn.lua")
    try:
        ev._call(fn, [])
    except Exception as ex:
        print("RUNTIME ERROR:", type(ex).__name__, ex)
        out = "\n".join(ev._out) if getattr(ev, "_out", None) else ""
        if out:
            print(out)
        return 1

    out = "\n".join(ev._out) if ev._out else ""
    print(out)

    m = re.search(r"KOMBAJN_RESULT\s+(\d+)\s+(\d+)", out)
    if not m:
        print("Brak markera KOMBAJN_RESULT — nieudany przebieg.")
        return 1
    p, f = int(m.group(1)), int(m.group(2))
    print(f"---\nkombajn: PASS={p} FAIL={f}")
    return 0 if f == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
