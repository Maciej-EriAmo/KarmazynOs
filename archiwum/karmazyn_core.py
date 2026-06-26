"""
karmazyn_core.py — KarmazynOS Model Fundamentalny
==================================================
Implementacja modelu fundamentalnego v0.1

  PhiSpace   — medium systemu, geometria S^(n-1)
  Atom       — najmniejsza jednostka operacyjna, trajektoria w S^(n-1)
  Hologram   — wzorzec idei, żywa pamięć doświadczeń
  Bubble     — przestrzeń(φ₁, φ₂), dwa tryby: WORKSPACE i LIBRARY

Wymagania: numpy
Autor: KarmazynOS Project / Maciej Mazur, 2026
"""

from __future__ import annotations

import time
from collections import deque
from enum import Enum

import numpy as np


# ===========================================================================
# PRZESTRZEŃ φ — medium systemu
# ===========================================================================

class PhiSpace:
    """
    Medium w którym istnieje system.
    Nie jest kontenerem. Jest geometrią S^(n-1).

    Wszystkie byty systemu są właściwościami geometrycznymi tej przestrzeni.
    Separacja wynika z matematyki, nie z reguł dostępu.
    """

    def __init__(self, n_dimensions: int):
        if n_dimensions < 2:
            raise ValueError("PhiSpace wymaga co najmniej 2 wymiarów.")
        self.n = n_dimensions

    def normalize(self, vector) -> np.ndarray:
        """
        Rzutuje wektor na S^(n-1).
        Byt musi mieć kierunek semantyczny — zero vector nie istnieje.
        """
        v = np.array(vector, dtype=float)
        if v.shape[0] != self.n:
            raise ValueError(
                f"Niezgodność geometrii: przestrzeń {self.n}D, "
                f"wektor {v.shape[0]}D."
            )
        norm = np.linalg.norm(v)
        if norm < 1e-12:
            raise ValueError(
                "Zero vector cannot exist in PhiSpace. "
                "Byt musi mieć kierunek semantyczny."
            )
        return v / norm

    def metric(self, phi_x: np.ndarray, phi_y: np.ndarray) -> float:
        """
        Metryka systemu: phi_metric(x, y) = 1 - dot(x, y)
        Zakres [0, 2]: 0 = identyczne, 1 = ortogonalne, 2 = przeciwstawne.
        Jedyna metryka używana w całym systemie.
        """
        return float(1.0 - np.dot(phi_x, phi_y))

    def resonance(self,
                  vec_a: np.ndarray,
                  vec_b: np.ndarray,
                  tau: float) -> bool:
        """
        Rezonans: jedyna operacja komunikacji między bytami.
        Zwraca True jeśli cos(φ_a, φ_b) >= tau.
        """
        return float(np.dot(vec_a, vec_b)) >= tau

    def frechet_mean(self, vectors: list[np.ndarray],
                     max_iter: int = 20,
                     tol: float = 1e-6) -> np.ndarray:
        """
        Fréchet mean na sferze S^(n-1) — iteracyjny algorytm log/exp map.
        Geometrycznie poprawny środek ciężkości dla wektorów na sferze.
        Używany przez Hologram.build_signature i Hologram.evolve.
        """
        if not vectors:
            raise ValueError("frechet_mean: pusta lista wektorów.")
        if len(vectors) == 1:
            return self.normalize(vectors[0])

        stacked = np.stack([self.normalize(v) for v in vectors])
        mu = self.normalize(stacked.mean(axis=0))

        for _ in range(max_iter):
            dots     = np.clip(stacked @ mu, -1.0 + 1e-7, 1.0 - 1e-7)
            angles   = np.arccos(dots)
            tangents = stacked - dots[:, None] * mu[None, :]
            tan_norms = np.linalg.norm(tangents, axis=1, keepdims=True)

            valid    = tan_norms.flatten() > 1e-8
            log_vecs = np.zeros_like(stacked)
            log_vecs[valid] = (angles[valid, None] *
                               tangents[valid] / tan_norms[valid])

            gradient  = log_vecs.mean(axis=0)
            grad_norm = np.linalg.norm(gradient)
            if grad_norm < tol:
                break
            mu = self.normalize(mu + gradient)

        return mu


# ===========================================================================
# ATOM — najmniejsza jednostka operacyjna
# ===========================================================================

class Atom:
    """
    Najmniejsza jednostka operacyjna systemu.
    Punkt / trajektoria w S^(n-1).
    RAM only — podlega rozpadowi.

    Atom nie tworzy przestrzeni φ. Jest bytem w przestrzeni.
    """

    def __init__(self,
                 space: PhiSpace,
                 initial_vector,
                 entropy_threshold: float = 2.0,
                 max_trace: int = 100):
        self.space              = space
        self.current_pos        = self.space.normalize(initial_vector)
        self.trajectory_log     = deque([self.current_pos.copy()],
                                        maxlen=max_trace)
        self.entropy            = 0.0
        self.entropy_threshold  = entropy_threshold
        self.created_at         = time.monotonic()

    def move(self, delta_vector) -> None:
        """
        Ruch po S^(n-1) przez rzut na przestrzeń styczną.
        Entropia rośnie proporcjonalnie do kosztu ruchu.
        """
        if self.is_decayed():
            raise RuntimeError("Atom rozpadł się. Ruch niemożliwy.")

        delta         = np.array(delta_vector, dtype=float)
        # Rzut delty na przestrzeń styczną do obecnej pozycji
        delta_tangent = delta - (np.dot(delta, self.current_pos)
                                 * self.current_pos)
        new_pos       = self.space.normalize(self.current_pos + delta_tangent)

        movement_cost  = self.space.metric(self.current_pos, new_pos)
        self.entropy  += movement_cost
        self.current_pos = new_pos
        self.trajectory_log.append(self.current_pos.copy())

    def is_decayed(self) -> bool:
        """Atom rozpada się gdy zgromadzi krytyczną entropię."""
        return self.entropy >= self.entropy_threshold

    def get_trace(self) -> list[np.ndarray]:
        """Zwraca historię trajektorii jako listę wektorów."""
        return list(self.trajectory_log)


# ===========================================================================
# HOLOGRAM — żywa pamięć idei
# ===========================================================================

class Hologram:
    """
    Wzorzec idei skompresowany z doświadczeń.

    Nie przechowuje faktów — przechowuje wzorce myślenia i tworzenia.
    Wchodzi jako składnik φ₁ przy tworzeniu Bąbla.
    Jest niepodrabialny bo zawiera historię trajektorii twórcy.

    Im dłużej system pracuje tym trudniej podrobić profil rezonansu.
    """

    def __init__(self, space: PhiSpace, initial_vectors: list):
        self.space      = space
        self.signature  = self._build_signature(initial_vectors)
        self._experience_count = len(initial_vectors)

    def _build_signature(self, vectors: list) -> np.ndarray:
        """
        Sygnatura Hologramu = Fréchet mean trajektorii doświadczeń.
        Geometrycznie poprawny środek ciężkości na S^(n-1).
        """
        if not vectors:
            raise ValueError(
                "Hologram musi powstać z doświadczenia "
                "(niepustej trajektorii)."
            )
        norm_vectors = [self.space.normalize(v) for v in vectors]

        mean_vec = np.mean(norm_vectors, axis=0)
        if np.linalg.norm(mean_vec) < 1e-6:
            raise ValueError(
                "Hologram niespójny — trajektoria eksploruje "
                "wzajemnie sprzeczne kierunki semantyczne."
            )
        return self.space.frechet_mean(norm_vectors)

    def evolve(self, new_experience_vectors: list,
               weight: float = 0.3) -> None:
        """
        Hologram ewoluuje przez nowe doświadczenia.

        Nowe doświadczenia wpływają na sygnaturę proporcjonalnie do wagi.
        weight = 0.3: nowe doświadczenia mają 30% wpływu na sygnaturę.
        Chroni przed gwałtowną zmianą tożsamości Hologramu.

        Wywoływana gdy Atomy wracają ze śladem φ lub Bąble zanikają.
        """
        if not new_experience_vectors:
            return

        new_sig = self._build_signature(new_experience_vectors)

        # Interpolacja sferyczna (SLERP) między starą a nową sygnaturą
        blended = ((1.0 - weight) * self.signature
                   + weight * new_sig)

        if np.linalg.norm(blended) < 1e-6:
            # Doświadczenia sprzeczne z istniejącą sygnaturą — ignoruj
            return

        self.signature          = self.space.normalize(blended)
        self._experience_count += len(new_experience_vectors)

    @property
    def experience_count(self) -> int:
        """Liczba doświadczeń które ukształtowały Hologram."""
        return self._experience_count


# ===========================================================================
# BUBBLE — przestrzeń(φ₁, φ₂)
# ===========================================================================

class BubbleMode(Enum):
    WORKSPACE = "workspace"
    LIBRARY   = "library"


class Bubble:
    """
    Przestrzeń między φ₁ i φ₂.

    φ₁ zawiera Hologram jako składnik definicji.
    Granica jest matematycznie nieprzenikalna — wynika z geometrii S^(n-1).

    Dwa tryby:
      WORKSPACE — równanie predykcyjne z progiem θ, rozpad gdy przekroczony
      LIBRARY   — gromadzenie bez limitu czasu, zanika bez podtrzymania,
                  równanie predykcyjne określa możliwość rozrostu
    """

    def __init__(self,
                 space: PhiSpace,
                 phi1: Hologram,
                 phi2_vector,
                 theta: float,
                 mode: BubbleMode = BubbleMode.WORKSPACE,
                 load_weight: float = 0.05,
                 time_weight: float = 0.01,
                 neglect_weight: float = 0.02):
        """
        space          — medium systemu
        phi1           — Hologram definiujący tożsamość Bąbla
        phi2_vector    — drugi biegun przestrzeni
        theta          — próg rozpadu (WORKSPACE) lub niestabilności (LIBRARY)
        mode           — tryb działania Bąbla
        load_weight    — wpływ liczby Atomów na Ψ
        time_weight    — wpływ czasu na Ψ (WORKSPACE)
        neglect_weight — wpływ braku aktywności na Ψ (LIBRARY)
        """
        self.space          = space
        self.phi1           = phi1
        self.phi2           = self.space.normalize(phi2_vector)
        self.theta          = theta
        self.mode           = mode
        self.load_weight    = load_weight
        self.time_weight    = time_weight
        self.neglect_weight = neglect_weight

        self.psi            = 0.0
        self.time_lived     = 0.0
        self.ticks_inactive = 0.0
        self._psi_stale     = True

        # Dystans semantyczny φ₁→φ₂ — bazowy fundament Ψ
        self.base_distance  = self.space.metric(
            self.phi1.signature, self.phi2
        )

    # ── Równanie predykcyjne ─────────────────────────────────────────────────

    def update_psi(self, active_atoms: list[Atom]) -> float:
        """
        Oblicza stan równania predykcyjnego Ψ.

        WORKSPACE:
          Ψ = base_distance
              + entropia_atomów
              + obciążenie (n_atomów × load_weight)
              + czas (time_lived × time_weight)

        LIBRARY:
          Ψ = base_distance
              + brak_aktywności (ticks_inactive × neglect_weight)
              + drift Hologramu (zmiany sygnatury φ₁)

        Przekroczenie theta → rozpad.
        """
        self.time_lived  += 1.0
        self._psi_stale   = False

        if self.mode == BubbleMode.WORKSPACE:
            total_entropy = sum(a.entropy for a in active_atoms)
            load_factor   = len(active_atoms) * self.load_weight
            time_factor   = self.time_lived * self.time_weight

            self.psi = (self.base_distance
                        + total_entropy
                        + load_factor
                        + time_factor)

        elif self.mode == BubbleMode.LIBRARY:
            if active_atoms:
                self.ticks_inactive = 0.0
            else:
                self.ticks_inactive += 1.0

            # Drift Hologramu — aktualna odległość φ₁ od φ₂
            # (Hologram ewoluuje, base_distance może już nie odzwierciedlać
            #  rzeczywistego stanu)
            current_distance = self.space.metric(
                self.phi1.signature, self.phi2
            )
            neglect_factor = self.ticks_inactive * self.neglect_weight

            self.psi = current_distance + neglect_factor

        return self.psi

    def is_collapsed(self) -> bool:
        """
        Przekroczenie theta powoduje rozpad Bąbla.
        WORKSPACE: imploduje gdy przeciążony lub za stary.
        LIBRARY: zanika gdy nikt nie korzysta lub staje się niespójna.
        """
        if self._psi_stale:
            raise RuntimeError(
                "Psi nie zostało obliczone. "
                "Wywołaj update_psi() przed sprawdzeniem stanu Bąbla."
            )
        return self.psi > self.theta

    # ── Równanie rozrostu (LIBRARY) ───────────────────────────────────────────

    @staticmethod
    def psi_grow(source_size: float,
                 theta_size: float) -> tuple[bool, int]:
        """
        Równanie predykcyjne rozrostu biblioteki.

        Określa czy źródło mieści się w jednym Bąblu,
        a jeśli nie — ile Bąbli potrzeba.

        source_size  — rozmiar źródła (np. bajty, liczba elementów)
        theta_size   — maksymalny rozmiar jednego Bąbla

        Zwraca:
          (fits_in_one, n_bubbles_needed)

        Semantyka:
          źródło wypełnia tyle Bąbli ile potrzebuje — automatycznie.
          Użytkownik widzi bibliotekę.
          System widzi sieć Bąbli połączonych rezonansem.
        """
        if source_size <= 0:
            raise ValueError("source_size musi być > 0.")
        if theta_size <= 0:
            raise ValueError("theta_size musi być > 0.")

        import math
        n_bubbles = math.ceil(source_size / theta_size)
        return (n_bubbles == 1, n_bubbles)

    # ── Rezonans ─────────────────────────────────────────────────────────────

    def resonates_with(self, atom: Atom, tau: float) -> bool:
        """
        Sprawdza czy Atom rezonuje z tym Bąblem.
        Używa φ₁ (zawierającego Hologram) jako punktu referencyjnego.
        """
        return self.space.resonance(
            atom.current_pos, self.phi1.signature, tau
        )


# ===========================================================================
# TESTY
# ===========================================================================

def _run_tests() -> None:
    print("=" * 60)
    print("karmazyn_core.py — testy jednostkowe")
    print("=" * 60)

    passed = failed = 0

    def chk(name: str, ok: bool, detail: str = "") -> None:
        nonlocal passed, failed
        print(f"  {'OK' if ok else 'XX'}  {name}")
        if detail and not ok:
            print(f"      {detail}")
        if ok:
            passed += 1
        else:
            failed += 1

    space = PhiSpace(n_dimensions=15)

    # ── PhiSpace ─────────────────────────────────────────────────────────────
    print("\n[1] PhiSpace")
    v = space.normalize([1.0] + [0.0] * 14)
    chk("normalize: norma = 1", abs(np.linalg.norm(v) - 1.0) < 1e-9)
    chk("metric(x,x) = 0", abs(space.metric(v, v)) < 1e-9)
    w = space.normalize([0.0, 1.0] + [0.0] * 13)
    chk("metric(e0,e1) = 1 (ortogonalne)", abs(space.metric(v, w) - 1.0) < 1e-9)
    chk("resonance: identyczne >= 0.9", space.resonance(v, v, 0.9))
    chk("resonance: ortogonalne < 0.9", not space.resonance(v, w, 0.9))

    try:
        space.normalize(np.zeros(15))
        chk("zero vector raises", False)
    except ValueError:
        chk("zero vector raises", True)

    # ── Atom ─────────────────────────────────────────────────────────────────
    print("\n[2] Atom")
    rng = np.random.default_rng(42)
    a = Atom(space, rng.standard_normal(15), entropy_threshold=1.0,
             max_trace=10)
    chk("Atom na S^14", abs(np.linalg.norm(a.current_pos) - 1.0) < 1e-9)
    chk("nie rozpadł się na starcie", not a.is_decayed())

    # Poruszamy atomem aż do rozpadu
    for _ in range(50):
        if a.is_decayed():
            break
        a.move(rng.standard_normal(15) * 0.5)

    chk("Atom rozpadł się po wystarczającym ruchu", a.is_decayed())

    try:
        a.move(rng.standard_normal(15))
        chk("move po rozpadzie raises", False)
    except RuntimeError:
        chk("move po rozpadzie raises", True)

    chk("trajectory_log nie przekracza max_trace",
        len(a.trajectory_log) <= 10)

    # ── Hologram ─────────────────────────────────────────────────────────────
    print("\n[3] Hologram")
    vecs = [rng.standard_normal(15) for _ in range(20)]
    h = Hologram(space, vecs)
    chk("sygnatura na S^14",
        abs(np.linalg.norm(h.signature) - 1.0) < 1e-9)
    chk("experience_count = 20", h.experience_count == 20)

    sig_before = h.signature.copy()
    h.evolve([rng.standard_normal(15) for _ in range(5)], weight=0.3)
    chk("sygnatura zmienia się po evolve",
        not np.allclose(h.signature, sig_before))
    chk("sygnatura nadal na S^14 po evolve",
        abs(np.linalg.norm(h.signature) - 1.0) < 1e-9)
    chk("experience_count rośnie", h.experience_count == 25)

    try:
        Hologram(space, [])
        chk("pusty Hologram raises", False)
    except ValueError:
        chk("pusty Hologram raises", True)

    # ── Bubble WORKSPACE ─────────────────────────────────────────────────────
    print("\n[4] Bubble — tryb WORKSPACE")
    phi2 = space.normalize(rng.standard_normal(15))
    b_ws = Bubble(space, h, phi2, theta=3.0,
                  mode=BubbleMode.WORKSPACE,
                  load_weight=0.05,
                  time_weight=0.01)

    chk("base_distance >= 0", b_ws.base_distance >= 0)

    try:
        b_ws.is_collapsed()
        chk("is_collapsed bez update_psi raises", False)
    except RuntimeError:
        chk("is_collapsed bez update_psi raises", True)

    atoms = [Atom(space, rng.standard_normal(15)) for _ in range(3)]
    psi_val = b_ws.update_psi(atoms)
    chk("psi > 0 po update", psi_val > 0)
    chk("is_collapsed nie podnosi po normalnym stanie",
        not b_ws.is_collapsed())

    # Forcuj rozpad przez wiele ticków
    for _ in range(500):
        b_ws.update_psi(atoms)
    chk("Bąbel Workspace rozpada się po czasie", b_ws.is_collapsed())

    # ── Bubble LIBRARY ────────────────────────────────────────────────────────
    print("\n[5] Bubble — tryb LIBRARY")
    h2 = Hologram(space, [rng.standard_normal(15) for _ in range(10)])
    phi2_lib = space.normalize(rng.standard_normal(15))
    b_lib = Bubble(space, h2, phi2_lib, theta=2.0,
                   mode=BubbleMode.LIBRARY,
                   neglect_weight=0.05)

    # Aktywna — nie powinna zanikać
    b_lib.update_psi([Atom(space, rng.standard_normal(15))])
    chk("Biblioteka aktywna nie zanika", not b_lib.is_collapsed())

    # Nieaktywna — powinna zanikać
    for _ in range(100):
        b_lib.update_psi([])   # brak Atomów
    chk("Biblioteka zanika bez podtrzymania", b_lib.is_collapsed())

    # ── psi_grow ─────────────────────────────────────────────────────────────
    print("\n[6] Bubble.psi_grow — równanie rozrostu")
    fits, n = Bubble.psi_grow(source_size=100, theta_size=200)
    chk("100 w 200 mieści się w jednym", fits and n == 1)

    fits, n = Bubble.psi_grow(source_size=500, theta_size=200)
    chk("500 w 200 wymaga 3 Bąbli", not fits and n == 3)

    fits, n = Bubble.psi_grow(source_size=200, theta_size=200)
    chk("200 w 200 dokładnie jeden", fits and n == 1)

    # ── Rezonans Bubble ───────────────────────────────────────────────────────
    print("\n[7] Rezonans Bubble ↔ Atom")
    # Tworzymy Atom blisko sygnatury Hologramu
    h3     = Hologram(space, [space.normalize([1.0] + [0.0] * 14)])
    phi2_r = space.normalize([0.0] * 14 + [1.0])
    b_r    = Bubble(space, h3, phi2_r, theta=5.0)
    b_r.update_psi([])

    # Atom bliski φ₁ — powinien rezonować
    atom_close = Atom(space, [1.0, 0.1] + [0.0] * 13)
    chk("Atom bliski φ₁ rezonuje (tau=0.8)",
        b_r.resonates_with(atom_close, tau=0.8))

    # Atom daleki — nie powinien rezonować
    atom_far = Atom(space, [0.0] * 14 + [1.0])
    chk("Atom daleki nie rezonuje (tau=0.8)",
        not b_r.resonates_with(atom_far, tau=0.8))

    # ── Podsumowanie ──────────────────────────────────────────────────────────
    total = passed + failed
    print(f"\n{'=' * 60}")
    print(f"Wyniki: {passed}/{total}")
    if failed == 0:
        print("PASS — model fundamentalny KarmazynOS operacyjny")
    else:
        print(f"FAIL — {failed} testów nie przeszło")
    print("=" * 60)


if __name__ == "__main__":
    _run_tests()
