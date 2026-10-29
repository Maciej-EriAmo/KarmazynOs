"""Mostek importu: karmazyn.py szuka hss_demo obok siebie.

Pełna implementacja jest w karmazyn_hss (wielobitowy Ring-LWE).
"""
from karmazyn_hss import (  # noqa: F401
    HSSDaemon,
    HistoryEntry,
    N,
    Q,
    RLWEResult,
    decrypt_multibit,
    kdf,
)
