"""Przenośne discovery jądra / monorepo (bez ścieżek developerskich).

Kolejność kandydatów na sys.path (katalogi z karmazyn_kernel):
  1) KARMAZYN_KERNEL / KARMAZYN_KERNEL_HOME
  2) monorepo: LUA/../kernel  (KarmazynOs/kernel)
  3) monorepo: LUA/..         (lustra karmazyn_kernel w root)
  4) sibling:  LUA/../Kernel Karmazyn  (opcjonalny layout dev)
"""
from __future__ import annotations

import os
import sys


def lua_root() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def kernel_candidates(root: str | None = None) -> list[str]:
    root = root or lua_root()
    parent = os.path.dirname(root)
    env = os.environ.get("KARMAZYN_KERNEL") or os.environ.get("KARMAZYN_KERNEL_HOME")
    out: list[str] = []
    if env:
        out.append(os.path.abspath(env))
    out.extend(
        [
            os.path.join(parent, "kernel"),       # monorepo kernel/
            parent,                               # monorepo root (lustra)
            os.path.join(parent, "Kernel Karmazyn"),
            os.path.join(parent, "KarmazynOs"),    # gdy LUA jest siblingiem monorepo
            os.path.join(parent, "KarmazynOs", "kernel"),
        ]
    )
    # dedupe zachowując kolejność
    seen = set()
    uniq = []
    for p in out:
        if not p:
            continue
        ap = os.path.normpath(os.path.abspath(p))
        if ap not in seen:
            seen.add(ap)
            uniq.append(ap)
    return uniq


def _looks_like_kernel_dir(path: str) -> bool:
    if not path or not os.path.isdir(path):
        return False
    # karmazyn_kernel.py w katalogu lub w podkatalogu (pakiet)
    if os.path.isfile(os.path.join(path, "karmazyn_kernel.py")):
        return True
    if os.path.isfile(os.path.join(path, "karmazyn_kernel", "__init__.py")):
        return True
    return False


def ensure_kernel_on_path(root: str | None = None) -> str | None:
    """Dodaj pierwsze działające źródło jądra na sys.path. Zwraca wybraną ścieżkę lub None."""
    chosen = None
    for cand in kernel_candidates(root):
        if _looks_like_kernel_dir(cand):
            if cand not in sys.path:
                sys.path.insert(0, cand)
            chosen = cand
            break
    return chosen


def ensure_lua_package(root: str | None = None):
    """Zarejestruj katalog LUA jako pakiet karmazyn_lua na sys.modules."""
    import types

    root = root or lua_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    if "karmazyn_lua" not in sys.modules:
        pkg = types.ModuleType("karmazyn_lua")
        pkg.__path__ = [root]
        pkg.__file__ = os.path.join(root, "__init__.py")
        sys.modules["karmazyn_lua"] = pkg
    return root
