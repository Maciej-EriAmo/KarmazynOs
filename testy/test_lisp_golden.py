# -*- coding: utf-8 -*-
"""Comparative Lisp golden: Python kernel vs Rust kernel.

Same cases (lisp_golden.txt). Independent of crate versions.
  python -m unittest testy.test_lisp_golden -v
  python testy/test_lisp_golden.py
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

_TESTY = Path(__file__).resolve().parent
ROOT = _TESTY.parent
for p in (_TESTY, ROOT):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

import _path  # noqa: E402,F401
from lisp_golden import GOLDEN_FILE, check_output, load_sessions  # noqa: E402


def _python_eval_session(steps):
    from karmazyn_exec import Evaluator
    from karmazyn_substrate import Store

    ev = Evaluator(Store(thermal=True))
    return [ev.eval_line(st.src) for st in steps]


def _shell_exe() -> Path | None:
    cands = [
        ROOT / "native" / "karmazyn_shell" / "target" / "release" / "karmazyn_shell.exe",
        ROOT / "native" / "karmazyn_shell" / "target" / "release" / "karmazyn_shell",
        ROOT / "dist" / "prefix" / "bin" / "karmazyn_shell.exe",
        ROOT / "native" / "karmazyn_shell" / "target" / "debug" / "karmazyn_shell.exe",
    ]
    for p in cands:
        if p.is_file():
            return p
    return None


def _parse_shell_batch(stdout: str, n: int) -> list[str]:
    """k$ <src>\\n<result>  — result may be missing (empty eval)."""
    lines = stdout.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("k$ "):
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if nxt.startswith("k$ ") or nxt.startswith("karmazyn_shell"):
                out.append("")
            else:
                out.append(nxt)
                i += 1
        i += 1
    if len(out) < n:
        out.extend([""] * (n - len(out)))
    return out[:n]


def _as_shell_lisp(src: str) -> str:
    """Bare symbols go through `lisp` (shell otherwise treats them as commands)."""
    t = src.strip()
    if t.startswith("("):
        return t
    return "lisp " + t


def _rust_eval_session(steps, exe: Path) -> list[str]:
    args = [str(exe)]
    for st in steps:
        args.extend(["-e", _as_shell_lisp(st.src)])
    r = subprocess.run(args, capture_output=True, text=True, timeout=30)
    if r.returncode not in (0, 1):
        raise RuntimeError(f"shell exit {r.returncode}: {r.stderr}")
    return _parse_shell_batch(r.stdout, len(steps))


class LispGoldenPython(unittest.TestCase):
    """Python kernel: karmazyn_substrate.Store + karmazyn_exec."""

    @classmethod
    def setUpClass(cls):
        cls.sessions = load_sessions()
        if not cls.sessions:
            raise unittest.SkipTest(f"empty golden {GOLDEN_FILE}")

    def test_all_sessions(self):
        fails = []
        for ses in self.sessions:
            got = _python_eval_session(ses.steps)
            for st, g in zip(ses.steps, got):
                err = check_output(g, st)
                if err:
                    fails.append(f"[python/{ses.name}] {st.src}  {err}")
        self.assertFalse(fails, "\n" + "\n".join(fails))


class LispGoldenRust(unittest.TestCase):
    """Rust kernel: karmazyn_lisp via karmazyn_shell (same cases)."""

    @classmethod
    def setUpClass(cls):
        cls.sessions = load_sessions()
        cls.exe = _shell_exe()
        if cls.exe is None:
            raise unittest.SkipTest(
                "brak karmazyn_shell — cargo build --release -p karmazyn_shell"
            )

    def test_all_sessions(self):
        fails = []
        for ses in self.sessions:
            got = _rust_eval_session(ses.steps, self.exe)
            for st, g in zip(ses.steps, got):
                err = check_output(g, st)
                if err:
                    fails.append(f"[rust/{ses.name}] {st.src}  {err}")
        self.assertFalse(fails, "\n" + "\n".join(fails))


class LispGoldenCompare(unittest.TestCase):
    """Raw: every step, python output == rust output."""

    @classmethod
    def setUpClass(cls):
        cls.sessions = load_sessions()
        cls.exe = _shell_exe()
        if cls.exe is None:
            raise unittest.SkipTest("brak karmazyn_shell — nie ma z czym porównać")

    def test_python_equals_rust(self):
        diffs = []
        for ses in self.sessions:
            py = _python_eval_session(ses.steps)
            rs = _rust_eval_session(ses.steps, self.exe)
            for st, a, b in zip(ses.steps, py, rs):
                if (a or "").strip() != (b or "").strip():
                    diffs.append(
                        f"[{ses.name}] {st.src}\n  python={a!r}\n  rust  ={b!r}"
                    )
        self.assertFalse(diffs, "kernels disagree:\n" + "\n".join(diffs))


if __name__ == "__main__":
    unittest.main()
