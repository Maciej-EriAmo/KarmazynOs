#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Utwórz sandbox/work z launcherami (idempotentne)."""
from __future__ import annotations

import os
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = Path(__file__).resolve().parent / "work"
EXP = WORK / "experiments"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        print(f"  keep {path.relative_to(ROOT)}")
        return
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"  write {path.relative_to(ROOT)}")


def main() -> int:
    print(f"sandbox bootstrap → {WORK}")
    EXP.mkdir(parents=True, exist_ok=True)

    write(
        WORK / "README.md",
        f"""# work/ — lokalna sesja

Root monorepo: `{ROOT}`

Nie commituj tego katalogu (gitignore). Notatki sesji trzymaj tutaj.
""",
    )

    write(
        WORK / "run_repl.ps1",
        f"""$Root = "{ROOT}"
$env:PYTHONPATH = "$Root;$Root\\software;$Root\\kernel;$Root\\native"
$env:KARMAZYN_SUBSTRATE = if ($env:KARMAZYN_SUBSTRATE) {{ $env:KARMAZYN_SUBSTRATE }} else {{ "native" }}
$env:KARMAZYN_LUA = "$Root\\LUA"
Set-Location $Root
python software\\karmazyn_boot.py @args
""",
    )

    write(
        WORK / "run_studio.ps1",
        f"""$Root = "{ROOT}"
$env:PYTHONPATH = "$Root;$Root\\software;$Root\\kernel;$Root\\native"
$env:KARMAZYN_SUBSTRATE = if ($env:KARMAZYN_SUBSTRATE) {{ $env:KARMAZYN_SUBSTRATE }} else {{ "native" }}
Set-Location $Root
python software\\karmazyn_studio.py @args
""",
    )

    write(
        WORK / "run_gate.ps1",
        f"""$Root = "{ROOT}"
Set-Location $Root
& "$Root\\scripts\\gate_product.ps1" @args
""",
    )

    write(
        WORK / "run_repl.sh",
        f"""#!/usr/bin/env bash
export ROOT="{ROOT}"
export PYTHONPATH="$ROOT:$ROOT/software:$ROOT/kernel:$ROOT/native"
export KARMAZYN_SUBSTRATE="${{KARMAZYN_SUBSTRATE:-native}}"
export KARMAZYN_LUA="$ROOT/LUA"
cd "$ROOT"
exec python software/karmazyn_boot.py "$@"
""",
    )

    write(
        EXP / "heat_lab.py",
        f'''# -*- coding: utf-8 -*-
"""Mini lab matrycy T — uruchom z sandbox/work/experiments."""
import os, sys
ROOT = r"{ROOT}"
sys.path[:0] = [ROOT, os.path.join(ROOT, "software"), os.path.join(ROOT, "kernel"),
                os.path.join(ROOT, "native")]
os.environ.setdefault("KARMAZYN_SUBSTRATE", "python")
from karmazyn_kernel import open_store
from karmazyn_io import attach_thermal, QueueIo

def main():
    s = open_store(backend="python", thermal=True)
    t = attach_thermal(s, QueueIo())
    print("before", t.stats())
    t.heat_input()
    print("after heat_input", t.stats())
    print("project", t.project_hot(limit=5, mark_visible=False))
    s.settle(20)
    print("after settle", t.stats())
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
''',
    )

    # unix exec bit best-effort
    for sh in (WORK / "run_repl.sh",):
        if sh.is_file():
            mode = sh.stat().st_mode
            sh.chmod(mode | stat.S_IXUSR)

    print("OK sandbox ready")
    print(f"  cd {WORK}")
    print("  .\\run_gate.ps1 -SkipLua")
    print("  .\\run_repl.ps1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
