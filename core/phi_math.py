# core/phi_math.py
import numpy as np
import math
import hashlib
from karmazyn_core import PhiSpace

class PhiPhysics:
    DIMENSIONS = 15
    STABILITY_THRESHOLD = 0.75
    _space = PhiSpace(n_dimensions=DIMENSIONS)

    @staticmethod
    def get_space() -> PhiSpace:
        return PhiPhysics._space

    # =========================
    # ARTYKUŁ II — PROJEKCJA φ
    # =========================
    @staticmethod
    def normalize_to_phi_space(x):
        """
        Wszystkie wejścia → 15D przestrzeń φ.
        WERSJA STABILNA: brak losowości w fallbacku.
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
        if norm > 0:
            return PhiPhysics._space.normalize(x)
        else:
            fallback = np.ones(PhiPhysics.DIMENSIONS) / math.sqrt(PhiPhysics.DIMENSIONS)
            return PhiPhysics._space.normalize(fallback)

    # =========================
    # DETERMINISTYCZNY HASH φ
    # =========================
    @staticmethod
    def _hash_to_vector(text: str):
        h = hashlib.sha256(text.encode()).digest()
        arr = np.frombuffer(h, dtype=np.uint8).astype(np.float32)
        return arr[:PhiPhysics.DIMENSIONS]

    @staticmethod
    def _resize_deterministic(v):
        out = np.zeros(PhiPhysics.DIMENSIONS, dtype=np.float32)
        m = min(len(v), PhiPhysics.DIMENSIONS)
        out[:m] = v[:m]
        return out

    # =========================
    # ARTYKUŁ IV — KOHERENCJA
    # =========================
    @staticmethod
    def harmonic_coherence(v1, v2):
        # We use metric mapping if needed, or simply dot product as coherence.
        # resonance handles thresholding. Let's keep harmonic_coherence returning dot product
        # but normalize just in case.
        return float(np.dot(PhiPhysics._space.normalize(v1), PhiPhysics._space.normalize(v2)))

    @staticmethod
    def is_coherent(v1, v2):
        return PhiPhysics._space.resonance(v1, v2, PhiPhysics.STABILITY_THRESHOLD)

    # =========================
    # ARTYKUŁ III — SNELL ROUTING
    # =========================
    @staticmethod
    def snell_refraction(v_in, v_target, n):
        # Snell Routing conceptually doesn't violate metric geometry, but we should make sure
        # it uses normalized vectors.
        v_in_norm = PhiPhysics._space.normalize(v_in)
        v_target_norm = PhiPhysics._space.normalize(v_target)

        cos_theta = np.clip(np.dot(v_in_norm, v_target_norm), -1.0, 1.0)
        sin_theta = math.sqrt(max(0, 1 - cos_theta**2))

        sin_theta2 = sin_theta / max(n, 1e-6)

        if sin_theta2 > 1.0:
            return {
                "penetrates": False,
                "coherence": cos_theta
            }

        return {
            "penetrates": True,
            "coherence": cos_theta
        }

    # =========================
    # ARTYKUŁ I — FIXED POINT
    # =========================
    @staticmethod
    def converges(v, attractor, eps=0.05):
        # Convergence implies distance < eps
        v_norm = PhiPhysics._space.normalize(v)
        attractor_norm = PhiPhysics._space.normalize(attractor)
        # Using the new metric:
        dist = PhiPhysics._space.metric(v_norm, attractor_norm)
        # Since metric is 1 - dot, and previous was euclidian norm(v - a), we adapt eps logic.
        # ||v - a||^2 = 2 - 2 dot(v, a) = 2 * metric(v, a). So ||v - a|| = sqrt(2 * metric).
        # We return if sqrt(2 * metric) < eps
        return math.sqrt(max(0, 2 * dist)) < eps

    @staticmethod
    def predict_vector_convergence(phi_in, phi_bubble, iterations=5):
        """
        Symuluje ewolucję wektora phi_in w polu przyciągania atraktora phi_bubble.
        Zwraca True, jeśli zbiega (koherencja po iteracjach >= STABILITY_THRESHOLD), w przeciwnym razie False.
        """
        v = PhiPhysics._space.normalize(np.copy(phi_in))
        attractor = PhiPhysics._space.normalize(np.copy(phi_bubble))
        alpha = 0.3

        # Odtwarzamy krok po kroku ruch wektora
        for i in range(iterations):
            # Przyciąganie przez bąbel
            v = v + alpha * (attractor - v)

            # Wektory mogą rosnąć/maleć, więc normalizujemy
            v = PhiPhysics._space.normalize(v)

        return PhiPhysics._space.resonance(v, attractor, PhiPhysics.STABILITY_THRESHOLD)
