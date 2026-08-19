# Repo root + golden kernel_python on sys.path (tests live in testy/).
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_s = str(ROOT)
if _s not in sys.path:
    sys.path.insert(0, _s)

import karmazyn_paths  # noqa: E402,F401
