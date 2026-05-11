# core/phi_math.py
import numpy as np
import math
import hashlib

class PhiPhysics:
    DIMENSIONS = 15
    STABILITY_THRESHOLD = 0.75

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
        return x / norm if norm > 0 else np.ones(PhiPhysics.DIMENSIONS) / math.sqrt(PhiPhysics.DIMENSIONS)

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
        return float(np.dot(v1, v2))

    @staticmethod
    def is_coherent(v1, v2):
        return PhiPhysics.harmonic_coherence(v1, v2) >= PhiPhysics.STABILITY_THRESHOLD

    # =========================
    # ARTYKUŁ III — SNELL ROUTING
    # =========================
    @staticmethod
    def snell_refraction(v_in, v_target, n):
        cos_theta = np.clip(np.dot(v_in, v_target), -1.0, 1.0)
        sin_theta = math.sqrt(1 - cos_theta**2)

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
        return np.linalg.norm(v - attractor) < eps
