# -*- coding: utf-8 -*-
"""Parse testy/lisp_golden.txt — portable Lisp cases (no kernel)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


GOLDEN_FILE = Path(__file__).resolve().parent / "lisp_golden.txt"


@dataclass
class Step:
    src: str
    expect: str | None = None
    needle: str | None = None  # blad: must contain this (case-insensitive)


@dataclass
class Session:
    name: str
    steps: list[Step] = field(default_factory=list)


def parse_golden(text: str) -> list[Session]:
    sessions: list[Session] = []
    cur: Session | None = None
    pending: Step | None = None

    def flush_pending():
        nonlocal pending
        if pending is not None:
            if cur is None:
                raise ValueError("step before === session")
            if pending.expect is None and pending.needle is None:
                raise ValueError(f"no expected output for: {pending.src}")
            cur.steps.append(pending)
            pending = None

    for raw in text.splitlines():
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped or stripped == "#" or stripped.startswith("# "):
            continue
        if stripped.startswith("==="):
            flush_pending()
            name = stripped[3:].strip() or f"s{len(sessions)}"
            cur = Session(name)
            sessions.append(cur)
            continue
        if stripped.startswith(">>>"):
            flush_pending()
            pending = Step(src=stripped[3:].strip())
            continue
        if stripped.startswith("!"):
            if pending is None:
                raise ValueError(f"orphan ! line: {stripped}")
            pending.needle = stripped[1:].strip()
            flush_pending()
            continue
        if pending is None:
            raise ValueError(f"orphan expect: {stripped}")
        pending.expect = stripped
        flush_pending()
    flush_pending()
    return sessions


def check_output(got: str, step: Step) -> str | None:
    got = (got or "").strip()
    if step.needle is not None:
        if not got.startswith("blad:"):
            return f"expected blad:…, got {got!r}"
        if step.needle.lower() not in got.lower():
            return f"expected blad containing {step.needle!r}, got {got!r}"
        return None
    if got != (step.expect or ""):
        return f"expected {step.expect!r}, got {got!r}"
    return None


def load_sessions(path: Path | None = None) -> list[Session]:
    p = path or GOLDEN_FILE
    return parse_golden(p.read_text(encoding="utf-8"))
