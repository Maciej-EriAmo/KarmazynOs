#!/usr/bin/env python3
"""Przelicz korpus językowy wyrocznią karmazyn_lua 1.1.2 i porównaj z *.out.

Pomija pliki wymienione w GAPS.md (tam Rust świadomie się różni).
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CRATE = HERE.parent
REPO = CRATE.parents[1]
LUA = REPO / "LUA"
GOLDEN = HERE / "golden"
GAPS = CRATE / "GAPS.md"


def main() -> int:
    sys.path.insert(0, str(LUA))
    sys.path.insert(0, str(REPO))
    from _paths import ensure_kernel_on_path, ensure_lua_package

    ensure_kernel_on_path(str(LUA))
    ensure_lua_package(str(LUA))
    import karmazyn_kernel
    from karmazyn_lua.lib import mount

    gaps = GAPS.read_text(encoding="utf-8")
    store = karmazyn_kernel.Store(thermal=True)
    ev = mount(store)
    failed = 0
    ran = 0
    for src_path in sorted(GOLDEN.glob("*.lua")):
        stem = src_path.stem
        if f"`{stem}.lua`" in gaps:
            print(f"SKIP {stem}  (GAPS)")
            continue
        out_path = src_path.with_suffix(".out")
        expected = out_path.read_text(encoding="utf-8").replace("\r\n", "\n").rstrip("\r\n")
        got = ev.eval_line(src_path.read_text(encoding="utf-8")).replace("\r\n", "\n").rstrip("\r\n")
        ran += 1
        if got != expected:
            failed += 1
            print(f"DIFF {stem}")
            print(f"  python: {got!r}")
            print(f"  golden: {expected!r}")
        else:
            print(f"OK   {stem}")
    print(f"compare: {ran - failed}/{ran}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
