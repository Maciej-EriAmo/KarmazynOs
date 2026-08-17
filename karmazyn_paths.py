# -*- coding: utf-8 -*-
"""Dane KarmazynOs — poza drzewem kodu (LOCALAPPDATA\\KarmazynOs)."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Dict, List


def data_home() -> Path:
    raw = (os.environ.get("KARMAZYN_DATA_HOME") or "").strip()
    if raw:
        return Path(raw).expanduser()
    local = (os.environ.get("LOCALAPPDATA") or "").strip()
    if local:
        return Path(local) / "KarmazynOs"
    return Path.home() / ".local" / "share" / "karmazynos"


def history_path() -> Path:
    p = data_home()
    p.mkdir(parents=True, exist_ok=True)
    return p / "history"


def runtime_data_dir() -> Path:
    p = data_home() / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def relocate_legacy(*, repo: Path | None = None) -> Dict[str, Any]:
    home = Path.home()
    dest = data_home()
    dest.mkdir(parents=True, exist_ok=True)
    moved: List[str] = []

    def move_file(src: Path, dst: Path) -> None:
        if not src.is_file():
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.is_file():
            shutil.copy2(src, dst)
            moved.append(src.name)
        try:
            src.unlink()
        except OSError:
            pass

    def move_dir(src: Path, dst: Path) -> None:
        if not src.is_dir():
            return
        if not dst.exists():
            shutil.copytree(src, dst)
            moved.append(str(src))
            shutil.rmtree(src, ignore_errors=True)

    move_file(home / ".karmazyn_history", history_path())
    move_dir(home / ".karmazyn", dest / "dot-karmazyn")
    if repo is None:
        repo = Path(__file__).resolve().parent
    move_dir(repo / "karmazyn_data", runtime_data_dir())
    readme = dest / "README.txt"
    if not readme.is_file():
        readme.write_text(
            "KarmazynOs data home — nie katalog projektu.\n",
            encoding="utf-8",
        )
    return {"home": str(dest), "moved": moved}
