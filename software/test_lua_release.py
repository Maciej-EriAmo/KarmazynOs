#!/usr/bin/env python3
"""Bramka release karmazyn_lua (alpha / pre / 0.9).

Uruchom z roota monorepo:

  python software/test_lua_release.py

Sprawdza:
  1) __version__
  2) unit testy LUA/
  3) host tools smoke
  4) kombajn.lua
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUA = os.path.join(ROOT, "LUA")
SOFTWARE = os.path.join(ROOT, "software")


def _run(label: str, args: list[str], cwd: str | None = None) -> int:
    print()
    print("=" * 60)
    print(f"  {label}")
    print("=" * 60)
    env = os.environ.copy()
    env.setdefault("KARMAZYN_LUA", LUA)
    env.setdefault("KARMAZYN_SUBSTRATE", "python")
    # software + root na path dla host/boot
    pp = env.get("PYTHONPATH", "")
    parts = [ROOT, SOFTWARE, os.path.join(ROOT, "kernel"), LUA]
    env["PYTHONPATH"] = os.pathsep.join(parts + ([pp] if pp else []))
    r = subprocess.run(args, cwd=cwd or ROOT, env=env)
    return int(r.returncode)


def main() -> int:
    print("karmazyn_lua release gate")
    print(f"  ROOT = {ROOT}")
    print(f"  LUA  = {LUA}")

    # 1) version
    sys.path.insert(0, LUA)
    # package as karmazyn_lua
    import types
    if "karmazyn_lua" not in sys.modules:
        pkg = types.ModuleType("karmazyn_lua")
        pkg.__path__ = [LUA]
        pkg.__file__ = os.path.join(LUA, "__init__.py")
        sys.modules["karmazyn_lua"] = pkg
    # kernel
    for p in (os.path.join(ROOT, "kernel"), ROOT):
        if p not in sys.path:
            sys.path.insert(0, p)
    try:
        # load __init__ version without full mount
        ver_path = os.path.join(LUA, "__init__.py")
        ns: dict = {}
        with open(ver_path, encoding="utf-8") as f:
            src = f.read()
        # tylko __version__ — unikaj import side effects
        for line in src.splitlines():
            if line.startswith("__version__"):
                exec(line, ns)
                break
        ver = ns.get("__version__", "?")
    except Exception as e:
        print(f"[FAIL] version: {e}")
        return 1
    print(f"  version = {ver}")
    if not str(ver).startswith("0.8"):
        print(f"[FAIL] oczekiwano wersji 0.8.x-alpha, jest {ver!r}")
        return 1
    print("[ OK ] version")

    fails = 0

    # 2) unit
    rc = _run("unit tests (LUA/_run_tests.py)", [sys.executable, "_run_tests.py"], cwd=LUA)
    if rc != 0:
        fails += 1
        print("[FAIL] unit tests")
    else:
        print("[ OK ] unit tests")

    # 3) host smoke
    rc = _run(
        "host tools smoke (software/test_host_tools.py)",
        [sys.executable, "test_host_tools.py", "-v"],
        cwd=SOFTWARE,
    )
    if rc != 0:
        fails += 1
        print("[FAIL] host smoke")
    else:
        print("[ OK ] host smoke")

    # 4) kombajn
    rc = _run("kombajn (LUA/kombajn_run.py)", [sys.executable, "kombajn_run.py"], cwd=LUA)
    if rc != 0:
        fails += 1
        print("[FAIL] kombajn")
    else:
        print("[ OK ] kombajn")

    # 5) lua_bin matrix (pass tools; skip top/nano)
    rc = _run(
        "lua_bin matrix (software/lua_bin_matrix.py --smoke)",
        [sys.executable, "lua_bin_matrix.py", "--smoke"],
        cwd=SOFTWARE,
    )
    if rc != 0:
        fails += 1
        print("[FAIL] lua_bin matrix")
    else:
        print("[ OK ] lua_bin matrix")

    print()
    print("=" * 60)
    if fails:
        print(f"  RELEASE GATE FAILED  ({fails} suite(s))  version={ver}")
        print("=" * 60)
        return 1
    print(f"  RELEASE GATE OK  karmazyn_lua {ver}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
