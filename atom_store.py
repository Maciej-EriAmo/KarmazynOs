"""
atom_store.py — AtomStore v1.0.0
=================================
Nowy moduł wygenerowany przez KarmazynLLM z idei BubbleStore.
Szkielet wygenerowany automatycznie, uzupełniony o brakujące metody.

AtomStore zarządza atomami w przestrzeni Φ analogicznie jak
BubbleStore zarządza bąblami — ale bez warstwy szyfrowania.
Atomy są lżejsze: brak fingerprint, brak bubble_key.
"""

import hashlib
import math
import numpy as np
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass, field


@dataclass
class Atom:
    id: str
    label: str
    S_struct: np.ndarray
    S_sem: np.ndarray
    content: bytes
    inode: str
    epoch_born: int
    recall_count: int = 0
    metadata: Dict = field(default_factory=dict)
    decay_start_epoch: Optional[int] = None
    decay_rate: float = 0.0

    def is_alive(self):
        return bool(self.content)

    def liveliness(self, current_epoch: int) -> float:
        if self.decay_start_epoch is None or self.decay_rate <= 0:
            return 1.0
        elapsed = max(0, current_epoch - self.decay_start_epoch)
        return math.exp(-self.decay_rate * elapsed)


class AtomStore:
    def __init__(self):
        self._a: Dict[str, Atom] = {}    # aid → Atom
        self._idx: Dict[str, str] = {}   # label → aid
        self._rev: set = set()           # revoked aids

    # ── zapis ────────────────────────────────────────────────────────────────

    def store(self, label: str, S_struct: np.ndarray, S_sem: np.ndarray,
              content: bytes, inode: str, epoch: int,
              metadata: dict = None) -> Atom:
        """Zapisuje atom do store. Zwraca Atom."""
        aid = "atom_" + hashlib.md5((label + str(epoch)).encode()).hexdigest()[:12]
        a = Atom(
            id=aid,
            label=label,
            S_struct=S_struct.copy(),
            S_sem=S_sem.copy(),
            content=content,
            inode=inode,
            epoch_born=epoch,
            metadata=metadata or {},
        )
        self._a[aid] = a
        self._idx[label] = aid
        return a

    # ── odczyt ────────────────────────────────────────────────────────────────

    def get_by_label(self, label: str) -> Optional[Atom]:
        """Zwraca atom po etykiecie lub None."""
        return self._a.get(self._idx.get(label))

    def get_by_id(self, aid: str) -> Optional[Atom]:
        """Zwraca atom po ID lub None."""
        return self._a.get(aid)

    # ── recall ────────────────────────────────────────────────────────────────

    def recall(self, q_sem: np.ndarray, current_epoch: int,
               k: int = 3, bias: float = 1.5) -> List[Tuple[float, Atom]]:
        """Zwraca k najlepiej pasujących atomów (score, atom)."""
        res = []
        for aid, a in self._a.items():
            if aid in self._rev or not a.is_alive():
                continue
            liv = a.liveliness(current_epoch)
            if liv <= 1e-9:
                continue
            sim = float(np.dot(q_sem, a.S_sem))
            score = sim * bias * liv
            res.append((score, a))
        res.sort(key=lambda x: x[0], reverse=True)
        for _, a in res[:k]:
            a.recall_count += 1
            if a.decay_start_epoch is not None:
                elapsed = current_epoch - a.decay_start_epoch
                a.decay_start_epoch = current_epoch - elapsed * 0.7
        return res[:k]

    # ── unieważnianie ─────────────────────────────────────────────────────────

    def revoke_by_label(self, label: str) -> bool:
        """Unieważnia atom — content znika, atom staje się szumem."""
        aid = self._idx.get(label)
        if aid in self._a:
            self._a[aid].content = b""
            self._rev.add(aid)
            return True
        return False

    # ── usuwanie ─────────────────────────────────────────────────────────────

    def remove_atom(self, label: str) -> bool:
        """Fizycznie usuwa atom ze store."""
        aid = self._idx.get(label)
        if aid and aid in self._a:
            del self._a[aid]
            del self._idx[label]
            if aid in self._rev:
                self._rev.remove(aid)
            return True
        return False

    def cleanup_revoked(self) -> int:
        """Usuwa unieważnione atomy. Zwraca liczbę usuniętych."""
        removed = 0
        for aid in list(self._rev):
            a = self._a.pop(aid, None)
            if a:
                if self._idx.get(a.label) == aid:
                    del self._idx[a.label]
                removed += 1
        self._rev.clear()
        return removed

    # ── decay ─────────────────────────────────────────────────────────────────

    def mark_for_decay(self, label: str, start_epoch: int,
                       rate: float) -> bool:
        a = self.get_by_label(label)
        if a:
            a.decay_start_epoch = start_epoch
            a.decay_rate = rate
            return True
        return False

    def refresh_atom(self, label: str) -> bool:
        a = self.get_by_label(label)
        if a:
            a.decay_start_epoch = None
            a.decay_rate = 0.0
            return True
        return False

    # ── właściwości ───────────────────────────────────────────────────────────

    @property
    def count(self) -> int:
        return len(self._a) - len(self._rev)

    @property
    def count_decaying(self) -> int:
        return sum(
            1 for a in self._a.values()
            if a.decay_start_epoch is not None and a.id not in self._rev
        )

    @property
    def all_active(self) -> List[Atom]:
        return [a for aid, a in self._a.items() if aid not in self._rev]
