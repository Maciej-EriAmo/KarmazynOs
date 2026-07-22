"""
KarmazynOS — Embedder Poziomów Sanktuarium
Tryb 'light': TF-IDF + hash (bez zewnętrznych zależności)
Tryb 'hrr': Holographic Reduced Representations

Wektory słów są DETERMINISTYCZNE (sha256 → seed), jak w karmazyn_hrr.name_to_vector.
"""
import hashlib
import os
from typing import Optional

import numpy as np


class LevelEmbedder:
    def __init__(self, seed: int = None, mode: str = "light", dim: int = 64):
        self.seed = seed if seed is not None else int.from_bytes(os.urandom(4), 'big')
        self.mode = mode
        self.dim = dim

    def _word_to_vec(self, word: str) -> np.ndarray:
        # Deterministyczny seed z treści słowa (nie z hash() Pythona — ten jest
        # randomizowany per-proces od Python 3.3 i psuje reprodukowalność).
        h = int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16) % (2**31)
        rng = np.random.default_rng(h)
        vec = rng.standard_normal(self.dim)
        n = np.linalg.norm(vec)
        return vec / n if n > 1e-12 else vec

    def _hrr_embed(self, words: list[str]) -> np.ndarray:
        if not words:
            return np.zeros(self.dim)
        vecs = [self._word_to_vec(w) for w in words]
        result = np.zeros(self.dim)
        for v in vecs:
            result = np.fft.ifft(np.fft.fft(result) * np.fft.fft(v)).real
            n = np.linalg.norm(result)
            result = result / (n + 1e-9) if n > 1e-12 else result
        return result

    def _light_embed(self, words: list[str]) -> np.ndarray:
        if not words:
            return np.zeros(self.dim)
        # Średnia wektorów ważona częstością
        freqs = {}
        for w in words:
            freqs[w] = freqs.get(w, 0) + 1
        result = np.zeros(self.dim)
        for w, cnt in freqs.items():
            result += self._word_to_vec(w) * cnt
        n = np.linalg.norm(result)
        return result / n if n > 1e-12 else result

    def generate_mission(self, words: list[str], system_temp: float = 0.8) -> dict:
        words = list(words) if words else ["pustka"]
        vec = self._hrr_embed(words) if self.mode == "hrr" else self._light_embed(words)
        rng = np.random.default_rng(int(np.sum(np.abs(vec)) * 1e5) % 2**31)
        # Generujemy 3–5 relikwii
        symbols = ["Δ", "Ω", "Ψ", "Σ", "Φ", "Θ", "Λ"]
        num_relikwii = 3 + int(rng.integers(0, 3))
        relikwie = []
        for i in range(num_relikwii):
            widoczny = bool(rng.choice([True, False], p=[0.7, 0.3]))
            s = f"{symbols[int(rng.integers(0, len(symbols)))]}-{int(rng.integers(1, 9))}"
            e = str(rng.choice(["Brama", "Klucz", "Cień", "Prawda", "Pustka"]))
            t_start = int(40 + rng.integers(0, 60))
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
