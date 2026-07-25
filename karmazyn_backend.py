#!/usr/bin/env python3
"""
karmazyn_backend.py — przełącznik substratu (Python | native Rust)
=================================================================
Maciej Mazur, Warsaw 2026

Do testów zgodności i (opcjonalnie) eksperymentalnego boota.

  KARMAZYN_SUBSTRATE=python   # domyślne — karmazyn_substrate.Store
  KARMAZYN_SUBSTRATE=native   # Rust DLL (native/karmazyn_substrate)
  KARMAZYN_SUBSTRATE=both     # tylko meta: test_compat uruchamia oba

CLI (test_substrate_compat / boot):
  --substrate python|native
  --native / --python

API:
  substrate_backend() -> "python" | "native"
  open_store(thermal=True, **kw) -> Store-like
  native_available() -> bool
"""

from __future__ import annotations

import os
import sys
from typing import Any, Optional, Type


_VALID = frozenset({"python", "native", "both"})


def substrate_backend(explicit: Optional[str] = None) -> str:
    """Aktualny backend: explicit > env > python. 'both' normalizowane do python
    przy open_store (both = tryb testów, nie runtime)."""
    raw = (explicit if explicit is not None else os.environ.get("KARMAZYN_SUBSTRATE", "python"))
    b = str(raw).strip().lower()
    if b in ("rust", "c", "dll", "ksub"):
        b = "native"
    if b not in _VALID:
        raise ValueError(
            f"KARMAZYN_SUBSTRATE={raw!r} — oczekiwano python|native|both"
        )
    return b


def apply_cli_substrate_flags(argv=None) -> Optional[str]:
    """Ustaw env z argv. Zwraca wybrany backend lub None."""
    argv = list(sys.argv if argv is None else argv)
    chosen = None
    if "--native" in argv:
        chosen = "native"
    if "--python" in argv:
        chosen = "python"
    if "--substrate" in argv:
        i = argv.index("--substrate")
        if i + 1 < len(argv):
            chosen = argv[i + 1]
    if chosen is not None:
        os.environ["KARMAZYN_SUBSTRATE"] = chosen
    return chosen


def native_available() -> bool:
    try:
        # prefer package path under native/
        root = os.path.dirname(os.path.abspath(__file__))
        if root not in sys.path:
            sys.path.insert(0, root)
        from native.karmazyn_substrate_native import native_available as nav
        return nav()
    except Exception:
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "native"))
            from karmazyn_substrate_native import native_available as nav
            return nav()
        except Exception:
            return False


def _load_native_store_class() -> Type:
    root = os.path.dirname(os.path.abspath(__file__))
    native_dir = os.path.join(root, "native")
    if native_dir not in sys.path:
        sys.path.insert(0, native_dir)
    from karmazyn_substrate_native import NativeStore
    return NativeStore


def open_store(thermal: bool = True, backend: Optional[str] = None, **kwargs: Any):
    """Utwórz Store na wybranym substracie.

    backend=None → KARMAZYN_SUBSTRATE (both → python).
    kwargs przekazywane do konstruktora (env_of, extra_reach, …).
    """
    b = substrate_backend(backend)
    if b == "both":
        b = "python"
    if b == "native":
        if not native_available():
            raise RuntimeError(
                "substrat native niedostępny — zbuduj: "
                "cd native/karmazyn_substrate && cargo build --release"
            )
        NativeStore = _load_native_store_class()
        return NativeStore(thermal=thermal, **kwargs)
    from karmazyn_substrate import Store
    return Store(thermal=thermal, **kwargs)


def backend_info() -> dict:
    b = substrate_backend()
    nav = native_available()
    ver = None
    if nav:
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "native"))
            from karmazyn_substrate_native import native_version
            ver = native_version()
        except Exception as e:
            ver = f"error: {e}"
    return {
        "backend": b,
        "native_available": nav,
        "native_version": ver,
        "env": os.environ.get("KARMAZYN_SUBSTRATE", ""),
    }


if __name__ == "__main__":
    apply_cli_substrate_flags()
    info = backend_info()
    print("substrate backend:", info)
    s = open_store(thermal=True)
    a = s.atom_new("probe", "x")
    print("atom", getattr(a, "id", a), "has", s.has_atom(getattr(a, "id", a)))
    print("stats", s.stats())
