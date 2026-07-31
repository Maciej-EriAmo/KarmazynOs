#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L1 Product host dry-run (exit 0 = pass). Not a full clean-VM install."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(name: str, ok: bool, detail: str = "") -> None:
    mark = " OK " if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        check.fails += 1  # type: ignore[attr-defined]


check.fails = 0  # type: ignore[attr-defined]


def main() -> int:
    os.chdir(ROOT)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT), str(ROOT / "software"), str(ROOT / "kernel"), str(ROOT / "native")]
        + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    env.setdefault("KARMAZYN_LUA", str(ROOT / "LUA"))

    print("=" * 40)
    print("  L1 Product host — dry-run")
    print(f"  root={ROOT}")
    print("=" * 40)

    # toolchain
    try:
        v = subprocess.check_output(["rustc", "--version"], text=True).strip()
        check("rustc", True, v)
    except Exception as e:
        check("rustc", False, str(e))

    try:
        v = subprocess.check_output([sys.executable, "--version"], text=True).strip()
        check("python", True, v)
    except Exception as e:
        check("python", False, str(e))

    sys.path[:0] = [str(ROOT), str(ROOT / "software"), str(ROOT / "kernel"), str(ROOT / "native")]
    try:
        from karmazyn_kernel import native_substrate_available

        check("native_substrate_available()", bool(native_substrate_available()))
    except Exception as e:
        check("native_substrate_available()", False, str(e))

    # gate
    gate = ROOT / "scripts" / "gate_product.ps1"
    if os.name == "nt" and gate.is_file() and "--skip-gate" not in sys.argv:
        r = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(gate), "-SkipLua"],
            cwd=str(ROOT),
            env=env,
        )
        check("gate_product", r.returncode == 0, f"exit={r.returncode}")
    elif "--skip-gate" in sys.argv:
        check("gate_product", True, "skipped")
    else:
        # unix fallback: unittest core
        r = subprocess.run(
            [sys.executable, "-m", "unittest", "software.test_io_thermal",
             "software.test_host_tools", "software.test_studio_sdl", "-q"],
            cwd=str(ROOT),
            env=env,
        )
        check("unittest core", r.returncode == 0)

    # boot stage=1 native
    env["KARMAZYN_SUBSTRATE"] = "native"
    env["KARMAZYN_IO"] = "queue"
    try:
        import karmazyn_boot as boot

        store, shell = boot.boot(verbose_events=False)
        ok = shell.thermal is not None and shell.thermal.stats().get("stage") == 1
        check("boot native stage=1", ok, type(store).__name__)
    except Exception as e:
        check("boot native stage=1", False, f"{type(e).__name__}: {e}")

    # studio check
    r = subprocess.run(
        [sys.executable, str(ROOT / "software" / "karmazyn_studio.py"), "--check", "--python"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    check("studio --check", r.returncode == 0 and "OK studio check" in (r.stdout + r.stderr))

    # honesty markers
    grub = (ROOT / "Documents" / "grub_loader_plan.md").read_text(encoding="utf-8", errors="ignore")
    check("grub plan marked NOT implemented", "NIE ZAIMPLEMENTOWANE" in grub or "PLAN TYLKO" in grub)
    proj = (ROOT / "PROJECT.md").read_text(encoding="utf-8", errors="ignore")
    check("PROJECT scope not full OS", "Nie jest" in proj or "nie jest" in proj.lower())

    print()
    if check.fails == 0:  # type: ignore[attr-defined]
        print("=" * 40)
        print("  L1 DRY-RUN PASS")
        print("  (czysta VM: ręcznie install_product.md)")
        print("=" * 40)
        return 0
    print("=" * 40)
    print(f"  L1 DRY-RUN FAIL ({check.fails} checks)")  # type: ignore[attr-defined]
    print("=" * 40)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
