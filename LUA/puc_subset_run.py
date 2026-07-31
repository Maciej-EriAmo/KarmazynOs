#!/usr/bin/env python3
"""Runner oficjalnego-stylu puc_subset (nie pełny lua-tests).

  python puc_subset_run.py
  exit 0 gdy wszystkie status=pass przechodzą.
"""
from __future__ import annotations

import json
import os
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

SUBSET = os.path.join(ROOT, "puc_subset")


def main() -> int:
    man_path = os.path.join(SUBSET, "manifest.json")
    with open(man_path, encoding="utf-8") as f:
        man = json.load(f)
    tests = man.get("tests") or []
    print(f"puc_subset: {man.get('description', '')}")
    print(f"kernel: {__import__('karmazyn_kernel').__file__}")
    print("---")

    passed = failed = skipped = 0
    for t in tests:
        name = t.get("file", "?")
        status = (t.get("status") or "pass").lower()
        path = os.path.join(SUBSET, name)
        if status == "skip":
            print(f"SKIP  {name}  ({t.get('note', '')})")
            skipped += 1
            continue
        if not os.path.isfile(path):
            print(f"FAIL  {name}  brak pliku")
            failed += 1
            continue
        with open(path, encoding="utf-8") as f:
            src = f.read()
        store = Store(thermal=True)
        session = store.bubble_new("puc-" + name)
        ev = mount(store, root_bubble=session, phi=compose_phi(b"puc", name.encode()), caps="default")
        try:
            ret = ev.run_source(src, chunkname="@" + name)
            print(f"PASS  {name}  ret={ret!r}")
            passed += 1
        except LuaError as e:
            print(f"FAIL  {name}  LuaError: {e}")
            failed += 1
        except Exception as ex:
            print(f"FAIL  {name}  {type(ex).__name__}: {ex}")
            failed += 1

    print("---")
    print(f"PUC_SUBSET  PASS={passed} FAIL={failed} SKIP={skipped}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
