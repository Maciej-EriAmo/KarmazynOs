"""
KarmazynOS — Embedder Poziomów Sanktuarium
Tryb 'light': TF-IDF + hash (bez zewnętrznych zależności)
Tryb 'hrr': Holographic Reduced Representations
"""
import numpy as np
import os
import json
from typing import Optional

class LevelEmbedder:
    def __init__(self, seed: int = None, mode: str = "light", dim: int = 64):
        self.seed = seed if seed is not None else int.from_bytes(os.urandom(4), 'big')
        self.mode = mode
        self.dim = dim

    def _word_to_vec(self, word: str) -> np.ndarray:
        h = abs(hash(word)) % (2**31)
        rng = np.random.RandomState(h)
        vec = rng.randn(self.dim)
        return vec / np.linalg.norm(vec)

    def _hrr_embed(self, words: list[str]) -> np.ndarray:
        vecs = [self._word_to_vec(w) for w in words]
        result = np.zeros(self.dim)
        for v in vecs:
            result = np.fft.ifft(np.fft.fft(result) * np.fft.fft(v)).real
            result = result / (np.linalg.norm(result) + 1e-9)
        return result

    def _light_embed(self, words: list[str]) -> np.ndarray:
        # Średnia wektorów ważona częstością
        freqs = {}
        for w in words:
            freqs[w] = freqs.get(w, 0) + 1
        result = np.zeros(self.dim)
        for w, cnt in freqs.items():
            result += self._word_to_vec(w) * cnt
        return result / np.linalg.norm(result)

    def generate_mission(self, words: list[str], system_temp: float = 0.8) -> dict:
        vec = self._hrr_embed(words) if self.mode == "hrr" else self._light_embed(words)
        rng = np.random.RandomState(int(np.sum(vec)*1e5) % 2**31)
        # Generujemy 3–5 relikwii
        symbols = ["Δ", "Ω", "Ψ", "Σ", "Φ", "Θ", "Λ"]
        num_relikwii = 3 + int(rng.randint(0, 3))
        relikwie = []
        for i in range(num_relikwii):
            widoczny = rng.choice([True, False], p=[0.7, 0.3])
            s = f"{symbols[rng.randint(0, len(symbols))]}-{rng.randint(1, 9)}"
            e = rng.choice(["Brama", "Klucz", "Cień", "Prawda", "Pustka"])
            t_start = int(40 + rng.randint(0, 60))
            relikwie.append({
                "id": f"rel_{i}",
                "S": s,
                "E": e,
                "T_start": t_start,
                "widoczny": widoczny,
                "wymaga_pryzmatu": "UMBRA" if not widoczny else None
            })
        cele = ["ustabilizuj_rel_0"]  # przykład
        return {
            "nazwa": " ".join(words).title(),
            "relikwie": relikwie,
            "cele": cele,
            "limit_ciszy": 2,
            "startowa_zywica": 10
        }