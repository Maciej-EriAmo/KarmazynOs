#!/usr/bin/env python3
"""
karmazyn_backend.py — szew do substratu.
Jedynym źródłem prawa jest native/karmazyn_substrate. open_store zwraca tylko native.

  KARMAZYN_SUBSTRATE=python | both   # odmowa
  KARMAZYN_ALLOW_PYTHON_SUBSTRATE    # nie otwiera drugiego silnika

Most:
  KARMAZYN_NATIVE_BRIDGE=pyo3|ctypes
"""

from __future__ import annotations

import os
import sys
from typing import Any, Optional, Type


_VALID = frozenset({"python", "native", "both"})


def substrate_strict() -> bool:
    """Flaga env. Nie otwiera Pythonowego silnika."""
    v = os.environ.get("KARMAZYN_SUBSTRATE_STRICT", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def allow_python_substrate() -> bool:
    """Flaga env. Nie otwiera Pythonowego silnika."""
    v = os.environ.get("KARMAZYN_ALLOW_PYTHON_SUBSTRATE", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _refuse_python(reason: str) -> None:
    raise RuntimeError(
        f"substrat: {reason}\n"
        "  Jedynym źródłem prawa jest native/karmazyn_substrate. Szew: open_store().\n"
        "  Zbuduj most: .\\native\\build_native.ps1\n"
        "Zob. Documents/SUBSTRATE_SEAL.md"
    )


def _candidate_roots():
    """Repo root + archived kernel_python dir."""
    here = os.path.dirname(os.path.abspath(__file__))
    yield here
    parent = os.path.dirname(here)
    if os.path.basename(here) == "kernel_python" and os.path.basename(parent) == "archiwum":
        yield os.path.dirname(parent)
    if parent and parent != here:
        yield parent


def _native_dirs():
    for root in _candidate_roots():
        yield os.path.join(root, "native")
        yield root  # allow `import native.*` from repo root


def native_available() -> bool:
    for d in _native_dirs():
        if d not in sys.path:
            sys.path.insert(0, d)
    try:
        from native.karmazyn_substrate_native import native_available as nav
        return nav()
    except Exception:
        try:
            from karmazyn_substrate_native import native_available as nav
            return nav()
        except Exception:
            return False


def resolve_default_backend() -> str:
    """Jedyny backend. Brak mostu jest błędem open_store, nie drugim silnikiem."""
    return "native"


def substrate_backend(explicit: Optional[str] = None) -> str:
    """Nazwa z argumentu albo ze środowiska. python i both nie otwierają silnika.

    Alias env: rust|c|dll|ksub → native.
    """
    if explicit is not None:
        raw = explicit
    else:
        env = os.environ.get("KARMAZYN_SUBSTRATE")
        if env is None or str(env).strip() == "":
            return resolve_default_backend()
        raw = env
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


def _load_native_store_class() -> Type:
    for d in _native_dirs():
        if d not in sys.path:
            sys.path.insert(0, d)
    from karmazyn_substrate_native import NativeStore
    return NativeStore


def _require_native(backend: Optional[str]) -> Type:
    b = substrate_backend(backend)
    if b != "native":
        _refuse_python(
            f"backend={b!r} odmówiony. "
            "KARMAZYN_SUBSTRATE=python, both i KARMAZYN_ALLOW_PYTHON_SUBSTRATE "
            "nie otwierają silnika."
        )
    if not native_available():
        _refuse_python("native niedostępny (brak mostu, brak drugiego silnika)")
    return _load_native_store_class()


def store_class(backend: Optional[str] = None) -> Type:
    """Klasa Store. Zawsze native."""
    return _require_native(backend)


def open_store(thermal: bool = True, backend: Optional[str] = None, **kwargs: Any):
    """Utwórz Store. Jedyny szew. Zawsze native/karmazyn_substrate."""
    native = _require_native(backend)
    return native(thermal=thermal, **kwargs)


def backend_info() -> dict:
    b = substrate_backend()
    nav = native_available()
    ver = None
    bridge = None
    if nav:
        try:
            for d in _native_dirs():
                if d not in sys.path:
                    sys.path.insert(0, d)
            from karmazyn_substrate_native import native_version, native_bridge
            ver = native_version()
            bridge = native_bridge()
        except Exception as e:
            ver = f"error: {e}"
    cls_name = None
    try:
        cls_name = store_class().__name__
    except Exception:
        cls_name = None
    return {
        "backend": b,
        "default": resolve_default_backend(),
        "native_available": nav,
        "native_version": ver,
        "native_bridge": bridge,  # pyo3 | ctypes | none
        "store_class": cls_name,  # NativeStore | Store
        "strict": substrate_strict(),
        "allow_python": allow_python_substrate(),
        "role": {
            "native": "jedyne źródło prawa (native/karmazyn_substrate)",
        },
        "env": os.environ.get("KARMAZYN_SUBSTRATE", ""),
        "seal": "Documents/SUBSTRATE_SEAL.md",
    }


if __name__ == "__main__":
    apply_cli_substrate_flags()
    info = backend_info()
    print("substrate backend:", info)
    s = open_store(thermal=True)
    a = s.atom_new("probe", "x")
    print(
        "store",
        type(s).__name__,
        "atom",
        getattr(a, "id", a),
        "has",
        s.has_atom(getattr(a, "id", a)),
        "backend",
        getattr(s, "native_backend", "python"),
    )
    print("stats", s.stats())
