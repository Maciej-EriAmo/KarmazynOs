# core/phi_math.py
# Most miedzy starym modelem (string S/E/T) a nowa geometria (wektor phi w S^14).
# Uzywany przez runtime.py jako warstwa adaptacyjna.

import hashlib
import math

import numpy as np

from karmazyn_core import PhiSpace


class PhiPhysics:
    DIMENSIONS          = 15
    STABILITY_THRESHOLD = 0.75
    _space              = PhiSpace(n_dimensions=DIMENSIONS)

    @staticmethod
    def get_space() -> PhiSpace:
        """Zwraca singleton przestrzeni phi uzywany przez caly system."""
        return PhiPhysics._space

    # =========================================================
    # ARTYKUL II - PROJEKCJA phi
    # =========================================================

    @staticmethod
    def normalize_to_phi_space(x) -> np.ndarray:
        """
        Wszystkie wejscia -> 15D przestrzen phi na S^14.
        Deterministyczny: identyczne wejscie zawsze daje identyczny wektor.

        Obsluguje:
          str          -> hash SHA-256 -> wektor 15D
          list/tuple   -> konwersja do float32
          np.ndarray   -> reshape jesli potrzeba
          inne         -> wektor zerowy -> fallback uniform
        """
        if isinstance(x, str):
            x = PhiPhysics._hash_to_vector(x)
        elif isinstance(x, (list, tuple, np.ndarray)):
            x = np.array(x, dtype=np.float32)
        else:
            x = np.zeros(PhiPhysics.DIMENSIONS, dtype=np.float32)

        if x.shape[0] != PhiPhysics.DIMENSIONS:
            x = PhiPhysics._resize_deterministic(x)

        norm = np.linalg.norm(x)
        if norm > 1e-9:
            return PhiPhysics._space.normalize(x)
        else:
            # Fallback deterministyczny: uniform na sferze
            fallback = np.ones(PhiPhysics.DIMENSIONS, dtype=np.float32)
            return PhiPhysics._space.normalize(fallback)

    # =========================================================
    # DETERMINISTYCZNY HASH phi
    # =========================================================

    @staticmethod
    def _hash_to_vector(text: str) -> np.ndarray:
        """SHA-256 tekstu -> pierwsze 15 bajtow jako float32."""
        h   = hashlib.sha256(text.encode('utf-8')).digest()
        arr = np.frombuffer(h, dtype=np.uint8).astype(np.float32)
        return arr[:PhiPhysics.DIMENSIONS]

    @staticmethod
    def _resize_deterministic(v: np.ndarray) -> np.ndarray:
        """Zmiana rozmiaru wektora do DIMENSIONS bez losowosci."""
        out    = np.zeros(PhiPhysics.DIMENSIONS, dtype=np.float32)
        m      = min(len(v), PhiPhysics.DIMENSIONS)
        out[:m] = v[:m]
        return out

    # =========================================================
    # ARTYKUL IV - KOHERENCJA
    # =========================================================

    @staticmethod
    def harmonic_coherence(v1, v2) -> float:
        """
        Koherencja semantyczna miedzy dwoma wektorami.
        Zwraca dot(norm(v1), norm(v2)) w [-1, 1].
        Rownowaznie: 1 - phi_metric(v1, v2).
        """
        a = PhiPhysics._space.normalize(np.array(v1, dtype=np.float32))
        b = PhiPhysics._space.normalize(np.array(v2, dtype=np.float32))
        return float(np.dot(a, b))

    @staticmethod
    def is_coherent(v1, v2) -> bool:
        """Zwraca True jesli rezonans >= STABILITY_THRESHOLD."""
        a = PhiPhysics._space.normalize(np.array(v1, dtype=np.float32))
        b = PhiPhysics._space.normalize(np.array(v2, dtype=np.float32))
        return PhiPhysics._space.resonance(a, b, PhiPhysics.STABILITY_THRESHOLD)

    # =========================================================
    # ARTYKUL III - SNELL ROUTING
    # =========================================================

    @staticmethod
    def snell_refraction(v_in, v_target, n: float) -> dict:
        """
        Refrakcja semantyczna (Prawo Snella).
        n = wspolczynnik refrakcji przestrzeni docelowej.

        Zwraca:
          {"penetrates": True/False, "coherence": float}
        """
        v_in_norm     = PhiPhysics._space.normalize(np.array(v_in,     dtype=np.float32))
        v_target_norm = PhiPhysics._space.normalize(np.array(v_target, dtype=np.float32))

        cos_theta = float(np.clip(np.dot(v_in_norm, v_target_norm), -1.0, 1.0))
        sin_theta = math.sqrt(max(0.0, 1.0 - cos_theta ** 2))
        sin_theta2 = sin_theta / max(n, 1e-6)

        if sin_theta2 > 1.0:
            return {"penetrates": False, "coherence": cos_theta}
        return {"penetrates": True,  "coherence": cos_theta}

    # =========================================================
    # ARTYKUL I - FIXED POINT / ZBIEZNOSC
    # =========================================================

    @staticmethod
    def converges(v, attractor, eps: float = 0.05) -> bool:
        """
        Sprawdza czy wektor v jest w promieniu eps od atraktora.
        Uzywa metryki sferycznej: ||v - a|| = sqrt(2 * phi_metric(v, a)).
        """
        v_norm        = PhiPhysics._space.normalize(np.array(v,        dtype=np.float32))
        attractor_norm = PhiPhysics._space.normalize(np.array(attractor, dtype=np.float32))
        dist          = PhiPhysics._space.metric(v_norm, attractor_norm)
        return math.sqrt(max(0.0, 2.0 * dist)) < eps

    @staticmethod
    def predict_vector_convergence(phi_in, phi_bubble,
                                   iterations: int = 5) -> bool:
        """
        Symuluje ewolucje wektora phi_in w polu przyciagania atraktora phi_bubble.
        Zwraca True jesli zbiega (koherencja po iteracjach >= STABILITY_THRESHOLD).

        Algorytm: iteracyjne przyciaganie z alpha=0.3, renormalizacja po kazdym kroku.
        """
        v        = PhiPhysics._space.normalize(np.array(phi_in,     dtype=np.float32))
        attractor = PhiPhysics._space.normalize(np.array(phi_bubble, dtype=np.float32))
        alpha    = 0.3

        for _ in range(iterations):
            # Przyciaganie liniowe w przestrzeni stycznej
            v = v + alpha * (attractor - v)
            # Renormalizacja na sfere
            v = PhiPhysics._space.normalize(v)

        return PhiPhysics._space.resonance(v, attractor, PhiPhysics.STABILITY_THRESHOLD)