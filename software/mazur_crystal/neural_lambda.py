"""
Opcjonalny λ_neural (PhiMost Faza E).

Domyślnie WYŁĄCZONY — zero wpływu na ranking / Λ.
Włączenie: PHIMOST_NEURAL_LAMBDA=1 oraz PHIMOST_ROOT wskazujący na model Ai.

Nie modyfikuje prawa GC slab/substrate.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Optional


def neural_lambda_enabled() -> bool:
    raw = os.environ.get("PHIMOST_NEURAL_LAMBDA", "0").strip().lower()
    return raw not in ("0", "false", "off", "no", "", "disable", "disabled")


def lambda_neural_weight() -> float:
    try:
        return float(os.environ.get("PHIMOST_LAMBDA_NEURAL", "0.2"))
    except ValueError:
        return 0.2


def _ensure_phimost_path() -> Optional[str]:
    # Bez PHIMOST_ROOT nic nie jest importowane spoza repo (N = None).
    root = os.environ.get("PHIMOST_ROOT", "").strip()
    if root and os.path.isdir(root) and root not in sys.path:
        sys.path.insert(0, root)
    return root if root and os.path.isdir(root) else None


def neural_N(atom: Any, probe: Any) -> Optional[float]:
    """Zwraca N∈[0,1] albo None (brak / flaga off / błąd importu)."""
    if not neural_lambda_enabled():
        return None
    if _ensure_phimost_path() is None:
        return None
    try:
        from mazur_neural import neural_component_for_pair  # type: ignore

        return neural_component_for_pair(atom, probe)
    except Exception:
        return None


def blend_relevance(
    R: float,
    M: float,
    atom: Any,
    probe: Any,
    *,
    lambda_R: float,
    lambda_M: float,
) -> float:
    """
    Klasycznie: λ_R·R + λ_M·M.
    Z flagą: (λ_R·R + λ_M·M + λ_N·N) / (λ_R+λ_M+λ_N).
    """
    N = neural_N(atom, probe)
    if N is None:
        return float(lambda_R) * float(R) + float(lambda_M) * float(M)
    ln = lambda_neural_weight()
    s = float(lambda_R) + float(lambda_M) + ln
    if s <= 1e-12:
        return float(R)
    return (float(lambda_R) * float(R) + float(lambda_M) * float(M) + ln * float(N)) / s
