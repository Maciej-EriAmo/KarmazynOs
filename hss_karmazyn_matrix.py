"""
hss_karmazyn_matrix.py — HSSKarmazynMatrix v2.1
================================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Poprawki:
  - dodano parametr n_sessions i **kwargs w __init__ dla kompatybilności
  - reszta bez zmian
"""

import hashlib
import json
import os
import re

import numpy as np

# =====================================================================
# ATOM
# =====================================================================

class Atom:
    """
    Atom termodynamiczny KarmazynOS.

    Atrybuty publiczne (czytane przez runtime i shell):
        id      — unikalny identyfikator (str)
        S       — sygnatura semantyczna (str, tekst)
        E       — emanacja / kontekst (str, tekst)
        T       — energia termodynamiczna 0..100 (float)
        T_max   — maksymalna energia (float, domyślnie 100.0)
        state   — HOT / WARM / COLD / TOMB (str)
        decay   — współczynnik zaniku λ (float, domyślnie 0.01)
        age     — liczba kroków od stworzenia (int)
        session — numer sesji (int)

    Wewnętrzne:
        _vec    — wektor numpy 64D (sygnatura w przestrzeni Φ)
        splamiony — bool (flaga korupcji)
    """

    __slots__ = (
        "id", "S", "E", "T", "T_max", "state",
        "decay", "age", "session", "_vec", "splamiony",
    )

    def __init__(self, id: str, S: str, E: str, T: float,
                 T_max: float = 100.0, decay: float = 0.01,
                 session: int = 0, vec: np.ndarray = None):
        self.id        = id
        self.S         = S
        self.E         = E
        self.T         = float(T)
        self.T_max     = float(T_max)
        self.decay     = float(decay)
        self.age       = 0
        self.session   = session
        self.splamiony = False
        self._vec      = vec if vec is not None else np.zeros(64, dtype=np.float32)
        self.state     = _classify(self.T)

    def __getitem__(self, key):
        if key == 'label': return self.id
        if key == 'S': return self._vec
        if key == 'T': return self.T
        if key == 'session': return self.session
        raise KeyError(key)

    def __setitem__(self, key, value):
        if key == 'T': self.T = float(value)
        elif key == 'S': self._vec = value
        else: raise KeyError(f"Cannot set {key} via dict interface")

    def get(self, key, default=None):
        try: return self[key]
        except KeyError: return default

    def __repr__(self):
        return f"Atom({self.id!r} T={self.T:.1f} state={self.state})"


def _classify(T: float) -> str:
    if T >= 70: return "HOT"
    if T >= 30: return "WARM"
    if T >= 1:  return "COLD"
    return "TOMB"


# =====================================================================
# HSS KARMAZYN MATRIX v2.1
# =====================================================================

class AtomsWrapper:
    """Wrapper supporting both atoms() call and direct iteration over atoms."""
    def __init__(self, matrix):
        self.matrix = matrix
        self._list_cache = None
        self._cache_time = -1

    def _get_list(self):
        if self._list_cache is None or self._cache_time != self.matrix.time:
            self._list_cache = list(self.matrix._atoms.values())
            self._cache_time = self.matrix.time
        return self._list_cache

    def __iter__(self):
        return iter(self.matrix._atoms.values())

    def __call__(self):
        return self._get_list()

    def __len__(self):
        return len(self.matrix._atoms)

    def __getitem__(self, index):
        return self._get_list()[index]

    def clear(self):
        """Clears all atoms from the matrix."""
        self.matrix._atoms.clear()
        self._list_cache = None

class HSSKarmazynMatrix:
    """
    Macierz termodynamiczna KarmazynOS.

    Zarządza atomami i ich ewolucją termodynamiczną.
    Eksportuje interfejs kompatybilny z SanctuaryRuntime v1.x i shell.py.
    """

    def __init__(self, dim: int = 64, n_sessions: int = 1, lambd: float = 0.01, seed: int = 42, **kwargs):
        """
        n_sessions oraz kwargs są ignorowane – zapewniają kompatybilność z KarmazynOS.
        """
        self.dim    = dim
        self.lambd  = lambd          # globalny współczynnik zaniku
        self.time   = 0
        self.rng    = np.random.default_rng(seed)
        self._atoms: dict = {}       # id → Atom (wewnętrzny storage)

    # ================================================================
    # INTERFEJS PUBLICZNY
    # ================================================================

    @property
    def atoms(self):
        """
        Zwraca wrapper wspierający iterację i wywołanie atoms().
        """
        return AtomsWrapper(self)

    def create_atom(self, id: str, S: str, E: str,
                    T: float, decay: float = 0.01,
                    session: int = 0) -> Atom:
        """
        Tworzy nowy atom.
        T może być w skali 0..100 (standardowa) lub 0..1 (jeśli T <= 1.0,
        automatycznie skalowane do 0..100).
        """
        if id in self._atoms:
            raise ValueError(f"Atom '{id}' już istnieje")

        # Normalizacja T: .karm używa 0..1, gra używa 0..100
        T_norm = T * 100.0 if T <= 1.0 else float(T)
        T_norm = max(1.0, min(100.0, T_norm))

        vec  = self._embed(f"{S} {E}")
        atom = Atom(id=id, S=S, E=E, T=T_norm,
                    T_max=100.0, decay=decay,
                    session=session, vec=vec)
        self._atoms[id] = atom
        return atom

    def get_atom(self, id: str):
        """Zwraca atom lub None."""
        return self._atoms.get(id)

    def has_atom(self, id: str) -> bool:
        return id in self._atoms

    def step(self):
        """
        Jeden krok termodynamiczny.

        Dla każdego atomu:
            T = T * (1 - lambd) * exp(-decay * age)

        Emituje zdarzenia przez yield (atom, event_type):
            "tick"          — każdy żywy atom
            "state_changed" — zmiana HOT/WARM/COLD
            "vacuum_decay"  — przejście do TOMB

        Usuwa atomy TOMB z rejestru.
        Zgodne z runtime.py który iteruje: for atom, event in matrix.step()
        """
        self.time += 1
        to_remove = []
        events    = []

        for atom in self._atoms.values():
            old_state = atom.state
            atom.age += 1

            # Termodynamiczny zanik: prosty wykładniczy
            atom.T *= (1.0 - self.lambd * atom.decay)
            atom.T  = max(0.0, atom.T)
            atom.state = _classify(atom.T)

            if atom.state == "TOMB":
                to_remove.append(atom.id)
                events.append((atom, "vacuum_decay"))
            else:
                events.append((atom, "tick"))
                if atom.state != old_state:
                    events.append((atom, "state_changed"))

        for id in to_remove:
            del self._atoms[id]

        return iter(events)

    # ================================================================
    # KOMPATYBILNOŚĆ Z ORYGINALNYM INTERFEJSEM
    # ================================================================

    def add_atom_vector(self, label: str, topic: str, vector: np.ndarray,
                        init_T: float, session: int = 0):
        """
        Interfejs kompatybilny z oryginalną HSSKarmazynMatrix.
        Używany przez kod który nie był jeszcze zaktualizowany.
        init_T w skali 0..1 → konwertujemy do 0..100.
        """
        T_norm = init_T * 100.0 if init_T <= 1.0 else float(init_T)
        T_norm = max(1.0, min(100.0, T_norm))
        atom   = Atom(id=label, S=topic, E="", T=T_norm,
                      T_max=100.0, decay=0.01,
                      session=session, vec=vector.copy())
        self._atoms[label] = atom

    # ================================================================
    # SAVE / LOAD
    # ================================================================

    def save(self, path: str):
        """
        Zapisuje do:
          <base>.npz  — wektory S i T
          <base>.json — metadane atomów
        """
        base = path.replace(".npz", "")

        if not self._atoms:
            np.savez(base + ".npz",
                     S=np.zeros((0, self.dim), dtype=np.float32),
                     T=np.zeros(0, dtype=np.float32))
            with open(base + ".json", "w", encoding="utf-8") as f:
                json.dump({"time": self.time, "atoms": []}, f)
            return

        atom_list = list(self._atoms.values())
        S_arr = np.array([a._vec for a in atom_list], dtype=np.float32)
        T_arr = np.array([a.T    for a in atom_list], dtype=np.float32)
        np.savez(base + ".npz", S=S_arr, T=T_arr)

        meta = {
            "time": self.time,
            "atoms": [
                {
                    "id":      a.id,
                    "S":       a.S,
                    "E":       a.E,
                    "T_max":   a.T_max,
                    "decay":   a.decay,
                    "age":     a.age,
                    "session": a.session,
                    "state":   a.state,
                }
                for a in atom_list
            ],
        }
        with open(base + ".json", "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def load(self, path: str):
        """
        Wczytuje z <base>.npz + <base>.json.
        Obsługuje stary format (brak .json) — fallback do topic jako S.
        """
        base      = path.replace(".npz", "")
        npz_path  = base + ".npz"
        json_path = base + ".json"

        if not os.path.exists(npz_path):
            return

        data  = np.load(npz_path, allow_pickle=False)
        S_arr = data["S"]
        T_arr = data["T"]

        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            self.time   = int(meta.get("time", 0))
            self._atoms = {}
            for i, am in enumerate(meta.get("atoms", [])):
                if i >= len(S_arr):
                    break
                vec  = S_arr[i].astype(np.float32)
                T    = float(T_arr[i])
                atom = Atom(
                    id=am.get("id", f"atom_{i}"),
                    S=am.get("S", am.get("topic", "")),
                    E=am.get("E", ""),
                    T=T,
                    T_max=float(am.get("T_max", 100.0)),
                    decay=float(am.get("decay", 0.01)),
                    session=int(am.get("session", 0)),
                    vec=vec,
                )
                atom.age   = int(am.get("age", 0))
                atom.state = am.get("state", _classify(T))
                self._atoms[atom.id] = atom
        else:
            # Fallback: stary format bez .json
            self.time   = 0
            self._atoms = {}
            for i in range(len(S_arr)):
                vec  = S_arr[i].astype(np.float32)
                T    = float(T_arr[i])
                atom = Atom(
                    id=f"atom_{i}", S="", E="", T=T,
                    T_max=100.0, decay=0.01, vec=vec,
                )
                self._atoms[atom.id] = atom

    # ================================================================
    # HELPERS
    # ================================================================

    def _embed(self, text: str) -> np.ndarray:
        """Deterministyczny embedding tekstu → wektor 64D."""
        tokens = [w for w in re.split(r"\W+", text.lower()) if len(w) > 1]
        if not tokens:
            tokens = [text[:8] if text else "empty"]
        vec = np.zeros(self.dim, dtype=np.float32)
        for tok in set(tokens):
            seed = int(hashlib.md5(tok.encode()).hexdigest(), 16) % (2 ** 32)
            v    = np.random.default_rng(seed).standard_normal(self.dim).astype(np.float32)
            vec += v
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 1e-9 else vec


# Alias dla kompatybilności z kodem który importuje HSSMatrix
HSSMatrix = HSSKarmazynMatrix