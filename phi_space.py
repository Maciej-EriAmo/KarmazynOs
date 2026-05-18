"""
phi_space.py — Wspólna przestrzeń semantyczna KarmazynOS
=========================================================
Jedna klasa PhiSpace używana przez karmazyn.py i runtime.py.
Zawiera embedding, TF‑IDF, rezonans, termodynamikę i tożsamość Φ².

v1.1 – dodano metody kompatybilności z runtime.py: register, embed, search, get, remove
       oraz parametr skip_matrix_step w step().
"""

import hashlib
import os
import numpy as np
from collections import Counter
from hss_karmazyn_matrix import HSSKarmazynMatrix
from hss_demo import N, Q
from typing import List, Optional, Tuple

# Stałe termodynamiczne
ALPHA        = 0.3
LAMBDA_DECAY = 0.1
DELTA_T_BASE = 5.0

STOPWORDS = {
    'i','w','z','na','do','ze','to','sie','nie','jest','jak','ale','po',
    'the','a','an','and','or','in','on','at','to','of','is','it','for',
    'co','byc','tak','ten','ta','te','ich','jej','jego','tym','przez',
}

# ── IDFCounter ──────────────────────────────────────────────────────
class IDFCounter:
    def __init__(self):
        self._freq  = Counter()
        self._ndocs = 0

    def add_doc(self, tokens):
        self._ndocs += 1
        for t in set(tokens):
            self._freq[t] += 1

    def idf(self, token):
        return float(np.log1p(self._ndocs / (1 + self._freq.get(token, 0))))


# ── PhiSpace ────────────────────────────────────────────────────────
class PhiSpace:
    def __init__(self, dim=15, n_sessions=1, seed=42, matrix=None):
        if matrix is not None:
            self._mx = matrix
        else:
            self._mx = HSSKarmazynMatrix(dim=dim, n_sessions=n_sessions,
                                         lambd=LAMBDA_DECAY, seed=seed)
        self.dim   = dim
        self._sid  = 0
        self._p2s  = os.urandom(32)
        self._sem: dict[str, np.ndarray] = {}
        self._rc:  dict[str, int]        = {}
        self._idf  = IDFCounter()
        self._tvac = self._measure_tvac()

    # ── Właściwości ──────────────────────────────────────────────────
    @property
    def t_vacuum(self):
        return self._tvac

    @property
    def epoch(self):
        return self._mx.time

    # ── Pomiar entropii próżni ──────────────────────────────────────
    def _measure_tvac(self):
        s = np.random.randint(0, Q, N, dtype=np.int64) % 256
        _, c = np.unique(s, return_counts=True)
        p = c / len(s)
        return float(-np.sum(p * np.log2(p + 1e-12)))

    # ── Embeddingi ──────────────────────────────────────────────────
    def embed_structural(self, c: bytes) -> np.ndarray:
        s = int(hashlib.md5(c).hexdigest(), 16) % (2**32)
        v = np.random.default_rng(s).normal(0, 1, self.dim).astype(np.float32)
        return v / (np.linalg.norm(v) + 1e-9)

    def embed_semantic(self, c: bytes, update=False) -> np.ndarray:
        try:
            text = c.decode('utf-8', errors='ignore').lower()
        except:
            return self.embed_structural(c)

        tokens = [w for w in text.split() if len(w) > 1 and w not in STOPWORDS]
        bigrams = [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
        all_t   = tokens + bigrams

        if not all_t:
            return self.embed_structural(c)

        if update:
            self._idf.add_doc(tokens)

        v = np.zeros(self.dim, dtype=np.float32)
        for t in all_t:
            w = self._idf.idf(t) * min(1.0, len(t) / 5.0)
            s = int(hashlib.md5(t.encode()).hexdigest(), 16) % (2**32)
            v += w * np.random.default_rng(s).normal(0, 1, self.dim).astype(np.float32)

        norm = np.linalg.norm(v)
        return v / norm if norm > 1e-9 else self.embed_structural(c)

    # ── Nowe metody dla kompatybilności z runtime.py ────────────────
    def register(self, label: str, text: str):
        """Rejestruje etykietę z wektorem semantycznym tekstu."""
        vec = self.embed_semantic(text.encode('utf-8'), update=True)
        self._sem[label] = vec
        self._rc[label]  = 0

    def embed(self, text: str) -> np.ndarray:
        """Zwraca wektor semantyczny dla podanego tekstu (string)."""
        return self.embed_semantic(text.encode('utf-8'))

    def search(self, query: str, candidates: List[str],
               k: int = 5) -> List[Tuple[str, float]]:
        """Wyszukuje najbardziej podobne etykiety do zapytania."""
        q_vec = self.embed(query)
        scores = []
        for lbl in candidates:
            v = self._sem.get(lbl)
            if v is None:
                continue
            sim = 1.0 - (np.linalg.norm(q_vec - v) / 2.0)  # odległość kosinusowa znormalizowana
            scores.append((lbl, sim))
        scores.sort(key=lambda x: x[1], reverse=True)
        for lbl, _ in scores[:k]:
            self._rc[lbl] = self._rc.get(lbl, 0) + 1
        return scores[:k]

    def get(self, label: str) -> Optional[np.ndarray]:
        """Zwraca wektor semantyczny dla etykiety (lub None)."""
        return self._sem.get(label)

    def remove(self, label: str):
        """Usuwa etykietę z przestrzeni semantycznej."""
        self._sem.pop(label, None)
        self._rc.pop(label, None)

    # ── Oryginalne metody z karmazyn.py ─────────────────────────────
    def phi2_bytes(self) -> bytes:
        return hashlib.sha256(self._p2s + b"phi2-v1").digest()

    def add(self, content: bytes, label="", init_T=DELTA_T_BASE):
        s_str = self.embed_structural(content)
        s_sem = self.embed_semantic(content, update=True)
        lbl = label or f"atom_{hashlib.md5(content).hexdigest()[:8]}"
        self._mx.add_atom_vector(label=lbl, topic="karmazyn", vector=s_str,
                                 init_T=init_T, session=self._sid)
        self._sem[lbl] = s_sem.copy()
        self._rc[lbl]  = 0
        return lbl

    def add_semantic_vector(self, vector: np.ndarray, label="", init_T=DELTA_T_BASE):
        lbl = label or f"atom_{hashlib.md5(vector.tobytes()).hexdigest()[:8]}"
        seed = int(hashlib.md5(vector.tobytes()).hexdigest(), 16) % (2**32)
        s_str = np.random.default_rng(seed).normal(0, 1, self.dim).astype(np.float32)
        s_str /= np.linalg.norm(s_str) + 1e-9
        self._mx.add_atom_vector(label=lbl, topic="karmazyn", vector=s_str,
                                 init_T=init_T, session=self._sid)
        self._sem[lbl] = vector.copy()
        self._rc[lbl]  = 0
        return lbl

    def recall(self, query: bytes, k=3):
        q_str = self.embed_structural(query)
        q_sem = self.embed_semantic(query)

        cands = []
        for a in self._mx.atoms:
            if a.get('session') != self._sid:
                continue
            lbl   = a.get('label', '')
            s_sem = self._sem.get(lbl, a['S'])

            sim_s = max(0.0, float(np.dot(q_str, a['S'])))
            sim_m = max(0.0, float(np.dot(q_sem, s_sem)))
            sim   = ALPHA * sim_s + (1 - ALPHA) * sim_m
            cands.append((sim * a['T'], a, sim))

        cands.sort(key=lambda x: x[0], reverse=True)

        result = []
        for _, a, sim in cands[:k]:
            a['T'] = a['T'] + 0.3 * (DELTA_T_BASE - a['T'])
            lbl = a.get('label', '')
            self._rc[lbl] = self._rc.get(lbl, 0) + 1
            result.append((a, sim))
        return result

    def recall_count(self, label):
        return self._rc.get(label, 0)

    def step(self, skip_matrix_step=False):
        """Wykonuje krok termodynamiczny i czyści martwe atomy z semantyki."""
        if not skip_matrix_step:
            self._mx.step()
        alive = {a['label'] for a in self._mx.atoms}
        self._sem = {k: v for k, v in self._sem.items() if k in alive}
        self._rc  = {k: v for k, v in self._rc.items()  if k in alive}
        return len(self._mx.atoms)

    def temperature(self):
        a = self._mx.atoms
        return float(np.mean([x['T'] for x in a])) if a else self._tvac

    
    def stats(self):
        return {
            "atoms":       len(self._mx.atoms),
            "epoch":       self.epoch,
            "temperature": self.temperature(),
            "t_vacuum()":    self._tvac,       # ← zwykłe pole, nie metoda
            "dim":         self.dim,
        }