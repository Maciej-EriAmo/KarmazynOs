"""Słownikowa macierz wektorów dla phi_space.

phi_space trzyma tu atomy jako {label, topic, S, T, session}.
Żywe prawo T×reach jest w substracie: AtomRegistry i Rust Store
(na kentry ten sam karmazyn_slab). Ta klasa zostaje przy API
add_atom_vector / get_atom / step.
step() mnoży T przez (1 - lambd). Domyślne lambd = 0.1
(LAMBDA_DECAY w phi_space). Próg usunięcia = 0.05.
"""
from __future__ import annotations

import numpy as np


class HSSKarmazynMatrix:
    def __init__(self, dim: int = 15, n_sessions: int = 1, lambd: float = 0.1, seed: int = 42):
        self.dim = int(dim)
        self.n_sessions = int(n_sessions)
        self.lambd = float(lambd)
        self.seed = int(seed)
        self.time = 0
        self.atoms: list = []
        self._floor = 0.05

    def add_atom_vector(self, label, topic="karmazyn", vector=None, init_T=5.0, session=0):
        vec = np.asarray(vector if vector is not None else np.zeros(self.dim), dtype=np.float32).reshape(-1).copy()
        existing = self.get_atom(label)
        if existing is not None:
            existing["S"] = vec
            existing["T"] = float(init_T)
            existing["topic"] = topic
            existing["session"] = session
            return existing
        atom = {
            "label": str(label),
            "topic": topic,
            "S": vec,
            "T": float(init_T),
            "session": session,
        }
        self.atoms.append(atom)
        return atom

    def get_atom(self, label):
        for atom in self.atoms:
            if atom.get("label") == label:
                return atom
        return None

    def step(self):
        self.time += 1
        keep = []
        cool = 1.0 - self.lambd
        for atom in self.atoms:
            atom["T"] = float(atom["T"]) * cool
            if atom["T"] >= self._floor:
                keep.append(atom)
        self.atoms = keep
        return self.time
