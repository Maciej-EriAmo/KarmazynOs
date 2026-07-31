#!/usr/bin/env python3
"""
start.py — menu startowe KarmazynOs (substrat Rust / Python)

  python start.py
  python start.py --rust
  python start.py --python
  python start.py --demo
  python start.py --native-check

Albo: Karmazyn.bat
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _prep_env(substrate: str) -> dict:
    env = os.environ.copy()
    env["KARMAZYN_SUBSTRATE"] = substrate
    # PATH cargo (opcjonalnie)
    cargo = Path.home() / ".cargo" / "bin"
    if cargo.is_dir():
        env["Path"] = str(cargo) + os.pathsep + env.get("Path", env.get("PATH", ""))
        env["PATH"] = env["Path"]
    # PYTHONPATH
    parts = [str(ROOT), str(ROOT / "kernel"), str(ROOT / "software"), str(ROOT / "native")]
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(parts + ([prev] if prev else []))
    return env


def _boot(substrate: str, extra_args: list | None = None) -> int:
    env = _prep_env(substrate)
    boot = ROOT / "karmazyn_boot.py"
    if (ROOT / "software" / "karmazyn_boot.py").is_file():
        boot = ROOT / "software" / "karmazyn_boot.py"
    cmd = [sys.executable, str(boot)] + list(extra_args or [])
    print(f"\n>>> {' '.join(cmd)}")
    print(f"    KARMAZYN_SUBSTRATE={substrate}")
    print(f"    PYTHONPATH={env['PYTHONPATH'][:120]}...")
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def _native_check() -> int:
    env = _prep_env("native")
    script = ROOT / "native" / "run_native_demo.py"
    if not script.is_file():
        print("Brak native/run_native_demo.py")
        return 1
    print("\n>>> weryfikacja native (Rust)")
    return subprocess.call([sys.executable, str(script), "--skip-dbase"], cwd=str(ROOT), env=env)


def _rust_only() -> int:
    env = _prep_env("native")
    ps1 = ROOT / "native" / "run_native.ps1"
    if not ps1.is_file():
        print("Brak native/run_native.ps1")
        return 1
    cmd = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(ps1),
        "-RustOnly",
    ]
    print("\n>>>", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def menu() -> int:
    while True:
        print()
        print("=" * 56)
        print("  KarmazynOs — start")
        print("=" * 56)
        print("  1) Boot  (Rust  / native)     ← domyślny produkcyjny")
        print("  2) Boot  (Python / reference)")
        print("  3) Boot demo  (Rust)")
        print("  4) Boot demo  (Python)")
        print("  5) Sprawdź native (smoke + GC)")
        print("  6) Tylko Rust core (cargo test + hello_store)")
        print("  7) Studio SDL2  (matryca T + shell)  ← native")
        print("  8) Studio SDL2  (python reference)")
        print("  0) Wyjście")
        print("-" * 56)
        choice = input("  wybór: ").strip()
        if choice in ("0", "q", "quit", "exit"):
            return 0
        if choice == "1":
            return _boot("native")
        if choice == "2":
            return _boot("python")
        if choice == "3":
            return _boot("native", ["--demo"])
        if choice == "4":
            return _boot("python", ["--demo"])
        if choice == "5":
            code = _native_check()
            print(f"  exit={code}")
            continue
        if choice == "6":
            code = _rust_only()
            print(f"  exit={code}")
            continue
        if choice == "7":
            return _boot("native", ["--studio"])
        if choice == "8":
            return _boot("python", ["--studio", "--python"])
        print("  nieznany wybór")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="KarmazynOs launcher")
    ap.add_argument("--rust", "--native", action="store_true", dest="rust")
    ap.add_argument("--python", action="store_true")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--native-check", action="store_true")
    ap.add_argument("--rust-only", action="store_true")
    ap.add_argument("--studio", action="store_true", help="Studio SDL2 × matryca T")
    ap.add_argument("--menu", action="store_true", help="wymuś menu")
    args, rest = ap.parse_known_args(argv)

    if args.native_check:
        return _native_check()
    if args.rust_only:
        return _rust_only()
    if args.studio:
        sub = "python" if args.python else "native"
        extra = ["--studio"] + (["--python"] if args.python else []) + list(rest)
        return _boot(sub, extra)
    if args.rust or args.python or args.demo:
        sub = "python" if args.python else "native"
        extra = ["--demo"] if args.demo else list(rest)
        return _boot(sub, extra)
    if rest and not args.menu:
        # nieznane argumenty → boot native z resztą
        return _boot("native", list(rest))
    return menu()


if __name__ == "__main__":
    raise SystemExit(main())
