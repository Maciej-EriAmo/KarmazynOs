#!/usr/bin/env python3
"""Bramka release karmazyn_lua 1.1.0 (produkcja gościa).

  python release_1_1.py

Kroki:
  1) __version__ == 1.1.x
  2) unit (_run_tests.py)
  3) kombajn
  4) puc_subset
  5) opcjonalnie host tools + lua_bin matrix (gdy monorepo Kernel dostępne)
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def _run(label: str, args: list[str], cwd: str | None = None) -> int:
    print()
    print("=" * 60)
    print(f"  {label}")
    print("=" * 60)
    r = subprocess.run(args, cwd=cwd or ROOT)
    return int(r.returncode)


def _kernel_root() -> str | None:
    cands = [
        os.environ.get("KARMAZYN_ROOT"),
        os.path.join(os.path.dirname(ROOT), "Kernel Karmazyn"),
        os.path.join(ROOT, "..", "Kernel Karmazyn"),
        r"C:\Users\drwis\Kernel Karmazyn",
    ]
    for c in cands:
        if c and os.path.isdir(os.path.join(c, "software")):
            return os.path.abspath(c)
    return None


def main() -> int:
    print("karmazyn_lua release gate 1.1")
    print(f"  LUA = {ROOT}")

    # 1) version
    ver = None
    with open(os.path.join(ROOT, "__init__.py"), encoding="utf-8") as f:
        for line in f:
            if line.startswith("__version__"):
                ns: dict = {}
                exec(line, ns)
                ver = ns.get("__version__")
                break
    print(f"  version = {ver}")
    if not (isinstance(ver, str) and (ver.startswith("1.1.") or ver.startswith("1.0."))):
        print(f"[FAIL] oczekiwano 1.1.x (lub 1.0.x), jest {ver!r}")
        return 1
    print("[ OK ] version")

    fails = 0

    def step(label: str, args: list[str], cwd: str | None = None) -> None:
        nonlocal fails
        rc = _run(label, args, cwd=cwd)
        if rc != 0:
            fails += 1
            print(f"[FAIL] {label}")
        else:
            print(f"[ OK ] {label}")

    step("unit tests", [sys.executable, "_run_tests.py"], cwd=ROOT)
    step("kombajn", [sys.executable, "kombajn_run.py"], cwd=ROOT)
    step("puc_subset", [sys.executable, "puc_subset_run.py"], cwd=ROOT)

    kroot = _kernel_root()
    if kroot:
        soft = os.path.join(kroot, "software")
        env = os.environ.copy()
        env.setdefault("KARMAZYN_LUA", ROOT)
        env.setdefault("KARMAZYN_SUBSTRATE", "python")
        pp = [
            kroot,
            soft,
            os.path.join(kroot, "kernel"),
            ROOT,
            env.get("PYTHONPATH", ""),
        ]
        env["PYTHONPATH"] = os.pathsep.join(p for p in pp if p)

        print()
        print("=" * 60)
        print("  host tools smoke")
        print("=" * 60)
        r = subprocess.run(
            [sys.executable, "test_host_tools.py", "-q"],
            cwd=soft,
            env=env,
        )
        if r.returncode != 0:
            # -q może nie istnieć — retry verbose
            r = subprocess.run(
                [sys.executable, "test_host_tools.py"],
                cwd=soft,
                env=env,
            )
        if r.returncode != 0:
            fails += 1
            print("[FAIL] host tools")
        else:
            print("[ OK ] host tools")

        print()
        print("=" * 60)
        print("  lua_bin matrix --smoke")
        print("=" * 60)
        r = subprocess.run(
            [sys.executable, "lua_bin_matrix.py", "--smoke"],
            cwd=soft,
            env=env,
        )
        if r.returncode != 0:
            fails += 1
            print("[FAIL] lua_bin matrix")
        else:
            print("[ OK ] lua_bin matrix")
    else:
        print()
        print("[SKIP] host tools / lua_bin — brak monorepo Kernel Karmazyn")

    print()
    print("=" * 60)
    if fails:
        print(f"  RELEASE 1.1.0 FAILED  ({fails} suite(s))  version={ver}")
        print("=" * 60)
        return 1
    print(f"  RELEASE 1.1.0 OK  karmazyn_lua {ver}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
