#!/usr/bin/env python3
"""Uruchom memviz.lua — cykl atomów na substracie z host API karmazyn.*.

  python memviz_run.py
  python memviz_run.py --substrate native|python

Wymaga: karmazyn_kernel + monorepo Kernel (software/karmazyn_host.py, lua_bin/memviz.lua).
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from _paths import ensure_kernel_on_path, ensure_lua_package  # noqa: E402

ensure_kernel_on_path(ROOT)
ensure_lua_package(ROOT)

# monorepo Kernel: software/ + lua_bin/
_KERNEL_CANDIDATES = [
    os.environ.get("KARMAZYN_ROOT"),
    os.path.join(os.path.dirname(ROOT), "Kernel Karmazyn"),
    os.path.join(ROOT, "..", "Kernel Karmazyn"),
    r"C:\Users\drwis\Kernel Karmazyn",
]
KERNEL_ROOT = None
for c in _KERNEL_CANDIDATES:
    if c and os.path.isdir(os.path.join(c, "software")):
        KERNEL_ROOT = os.path.abspath(c)
        break
if KERNEL_ROOT is None:
    print("ERROR: nie znaleziono monorepo Kernel Karmazyn (software/)", file=sys.stderr)
    sys.exit(2)

sys.path.insert(0, os.path.join(KERNEL_ROOT, "software"))
sys.path.insert(0, KERNEL_ROOT)

from karmazyn_kernel import Store, kernel_info  # noqa: E402
from karmazyn_lua.lib import mount  # noqa: E402
from karmazyn_lua.values import compose_phi, LuaError  # noqa: E402
from karmazyn_host import install_karmazyn_host  # noqa: E402
import karmazyn_lua as pkg  # noqa: E402

pkg.mount = mount
pkg.compose_phi = compose_phi

LUA_BIN = os.path.join(KERNEL_ROOT, "lua_bin")
MEMVIZ = os.path.join(LUA_BIN, "memviz.lua")


def main() -> int:
    backend = "default"
    for a in sys.argv[1:]:
        if a.startswith("--substrate="):
            os.environ["KARMAZYN_SUBSTRATE"] = a.split("=", 1)[1]
            backend = a.split("=", 1)[1]
        elif a == "--substrate" and sys.argv.index(a) + 1 < len(sys.argv):
            backend = sys.argv[sys.argv.index(a) + 1]
            os.environ["KARMAZYN_SUBSTRATE"] = backend

    if not os.path.isfile(MEMVIZ):
        print(f"ERROR: brak {MEMVIZ}", file=sys.stderr)
        return 2

    ki = kernel_info() if callable(kernel_info) else {}
    store = Store(thermal=True)
    session = store.bubble_new("memviz-session")
    phi = compose_phi(b"memviz", b"demo")
    ev = mount(store, root_bubble=session, phi=phi, caps="default")
    install_karmazyn_host(ev, store=store)

    print(f"kernel:  {__import__('karmazyn_kernel').__file__}")
    print(f"version: {ki.get('version', '?')}  store={ki.get('store_class', '?')}")
    sub = ki.get("substrate") or {}
    print(f"backend: {sub.get('backend', backend)}  native={sub.get('native_available')}")
    print(f"source:  {MEMVIZ}")
    print(f"host:    karmazyn.* {_host_ver(ev)}")
    print("---")

    try:
        with open(MEMVIZ, encoding="utf-8") as f:
            src = f.read()
        ret = ev.run_source(src, chunkname="@memviz.lua")
    except LuaError as e:
        print("ERROR:", ev.format_run_result(err=e))
        return 1
    except Exception as ex:
        print("RUNTIME ERROR:", type(ex).__name__, ex)
        out = "\n".join(ev._out) if getattr(ev, "_out", None) else ""
        if out:
            print(out)
        return 1

    print(ev.format_run_result(ret=ret))
    print("---")
    print("memviz: OK")
    return 0


def _host_ver(ev) -> str:
    try:
        return str(ev.eval_line("return karmazyn._VERSION"))
    except Exception:
        return "?"


if __name__ == "__main__":
    sys.exit(main())
