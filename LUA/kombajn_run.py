#!/usr/bin/env python3
"""Uruchom kombajn.lua na KarmazynLua + Kernel.

  python kombajn_run.py
  exit 0  → FAIL==0
  exit 1  → są błędy / FAIL>0
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from _paths import ensure_kernel_on_path, ensure_lua_package  # noqa: E402

ensure_kernel_on_path(ROOT)
ensure_lua_package(ROOT)

from karmazyn_kernel import Store  # noqa: E402
from karmazyn_lua.lib import mount  # noqa: E402
from karmazyn_lua.values import compose_phi, LuaError  # noqa: E402

import karmazyn_lua as pkg  # noqa: E402

pkg.mount = mount
pkg.compose_phi = compose_phi


def main() -> int:
    path = os.path.join(ROOT, "kombajn.lua")
    store = Store(thermal=True)
    session = store.bubble_new("kombajn-session")
    phi = compose_phi(b"kombajn", b"test")
    ev = mount(store, root_bubble=session, phi=phi, caps="default")

    print(f"kernel: {__import__('karmazyn_kernel').__file__}")
    print(f"phi:    {phi!r}")
    print(f"source: {path}")
    print("---")

    try:
        ret = ev.run_file(path, chunkname="@kombajn.lua")
    except LuaError as e:
        print("ERROR:", ev.format_run_result(err=e))
        return 1
    except Exception as ex:
        print("RUNTIME ERROR:", type(ex).__name__, ex)
        out = "\n".join(ev._out) if getattr(ev, "_out", None) else ""
        if out:
            print(out)
        return 1

    out = ev.format_run_result(ret=ret)
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
