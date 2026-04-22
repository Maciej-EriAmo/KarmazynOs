"""
Bubble Colony — Zadanie C: Synteza sesji badawczej przez pokolenia baniek

Analogia komórkowa:
    G0 = komórka macierzysta (szeroki rdzeń: publikowalność)
    G1 = komórka progenitorowa (rdzeń z G0 top-5)
    G2+ = komórki zróżnicowane (coraz węższa specjalizacja)

Cykl życia bańki:
    1. Otrzymuje rdzeń od poprzedniej generacji (lub startowy)
    2. Injektuje atomy zadania jako strumień
    3. Przez max_age-1 epok: T-competition (selekcja geometryczna)
    4. Zbiera top-k atomów → rdzeń następnej generacji
    5. Wszystkie atomy sesji umierają (max_age przekroczone)
    6. Rdzeń przekazany → NASTĘPNA GENERACJA
"""

import numpy as np
import math
import hashlib
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from karmazyn_matrix_v34 import KarmazynMatrix


# ============================================================
# Embeddings
# ============================================================

def embed_kw(kw: str, dim: int = 4096) -> np.ndarray:
    h = hashlib.md5(kw.encode()).hexdigest()
    seed = int(h, 16) % (2**32)
    v = np.random.default_rng(seed).normal(0, 1, dim)
    return v / np.linalg.norm(v)


def make_vec(content_kws: list, meta_kws: list,
             dim: int = 4096, mw: float = 0.7) -> np.ndarray:
    c = np.sum([embed_kw(k, dim) for k in content_kws], axis=0)
    m = np.sum([embed_kw(k, dim) for k in meta_kws],    axis=0)
    v = mw * m + (1 - mw) * c
    return v / np.linalg.norm(v)


def make_core_from_kws(kws: list, dim: int = 4096) -> np.ndarray:
    v = np.sum([embed_kw(k, dim) for k in kws], axis=0)
    return v / np.linalg.norm(v)


# ============================================================
# Atomy sesji — dekompozycja zadania C
# ============================================================

MH = ['novel', 'empirical', 'verified', 'contribution', 'clear', 'formal']
MM = ['empirical', 'verified', 'contribution']
ML = ['speculative', 'analogy', 'inspirational']

SESSION_ATOMS = [
    ('E1', 'Adaptive friction f=c/sqrt(d) — geometric derivation',        ['adaptive', 'friction'],       MH),
    ('E2', 'Survival condition k*sim > lambda*tau+f — 884% margin',        ['survival', 'threshold'],      MH),
    ('E3', 'Baseline SNR 20-150x vs HRR — geometry not temperature',       ['baseline', 'SNR'],            MH),
    ('E4', 'Embedding ablation cluster-driven not sequence',               ['ablation', 'cluster'],        MH),
    ('E5', 'Energy monotonicity 100% of 50 seeds post-epoch 20',           ['monotonicity', 'seeds'],      MH),
    ('E6', 'Hopfield benchmark — KM wins unsupervised, complementary',     ['Hopfield', 'benchmark'],      MH),
    ('E7', 'HSS routing analytic: core_overlap > gate/emission_sim',       ['routing', 'formula'],         MH),
    ('E8', 'Gamma isolation: 0 receptions, core_sim 0.997',                ['isolation', 'zero'],          MM),
    ('G1', 'Ontological immunity: sudden attack purifies core',            ['immunity', 'hostile'],        MH),
    ('G2', 'Adaptation 0.9457: trace follows continuous environment',      ['adaptation', 'correlation'],  MH),
    ('G3', 'E2/E3 asymmetry: one threshold, two input topologies',         ['asymmetry', 'topology'],      MH),
    ('G4', 'Observer-dependent: path-dependent projection operator',       ['observer', 'path'],           MM),
    ('G5', 'Population equilibrium 27.5 atoms, quasi-static drift',        ['equilibrium', 'bounded'],     MM),
    ('T1', 'Mean-field attractor class, replicator dynamics analogy',      ['mean-field', 'replicator'],   MM),
    ('T2', 'Trace selects admissible trajectories, not estimator',         ['subspace', 'admissible'],     MM),
    ('T3', 'bind(core,boundary) sim~0.98 — two novelty registers',        ['bind', 'boundary'],           MM),
    ('T4', 'Black hole / coherent jet analogy — inspirational',            ['analogy', 'horizon'],         ML),
    ('T5', 'Relational survival = f(geometric alignment) — key insight',   ['relational', 'alignment'],    MH),
    ('H1', 'HSS no-protocol geometry — system of visibility',              ['no-protocol', 'geometry'],    MH),
    ('H2', 'emission_sim: identity vs convergence single parameter',       ['emission', 'identity'],       MH),
    ('H3', 'Alpha-Beta emergent synchronization through field',            ['convergence', 'synchronization'], MM),
    ('H4', 'Genesis 6: boundary generation at horizon',                   ['genesis6', 'boundary'],       MM),
]


# ============================================================
# Jedna generacja
# ============================================================

def run_generation(
    core_vec: np.ndarray,
    atoms: list,
    gen_id: int,
    max_age: int = 50,
    top_k: int = 5,
    dim: int = 4096,
    verbose: bool = True,
) -> dict:
    """
    Jedna generacja bańki.

    Cykl:
      1. Inicjalizacja rdzenia + warmup 10 epok
      2. Iniekcja atomów przez bramę
      3. T-competition przez max_age-1 epok
      4. Kolekcja przeżałych (PRZED finalnym wygaśnięciem)
      5. Obliczenie rdzenia następnej generacji (top-k)

    Rozpad: deterministyczny — wszystkie atomy sesji
    mają wiek max_age po ostatniej epoce i umierają razem.
    """
    km   = KarmazynMatrix(dim=dim, seed=42 + gen_id)
    gate = (km.lambd * km.vac_threshold + km.friction) / km.k

    # Rdzeń — permanentny
    km.add_atom_vector(f'core_G{gen_id}', 'core', core_vec, init_T=2.5)
    km.atoms[-1]['permanent'] = True
    km.atoms[-1]['age']       = 0

    # Warmup
    for _ in range(10):
        for a in km.atoms:
            a['age'] = a.get('age', 0) + 1
        km.step()

    # Iniekcja
    admitted, rejected = [], []
    for atom_id, text, ckws, mkws in atoms:
        v   = make_vec(ckws, mkws, dim=dim)
        sim = float(np.dot(v, km.trace))
        if sim > gate:
            km.atoms.append({
                'label': atom_id, 'topic': 'session',
                'S': v, 'T': 1.5, 'age': 0,
                'permanent': False, 'text': text,
            })
            km._rebuild_trace()
            admitted.append(atom_id)
        else:
            rejected.append((atom_id, round(sim, 4), text[:50]))

    # T-competition: max_age-1 epok
    for _ in range(max_age - 1):
        for a in km.atoms:
            a['age'] = a.get('age', 0) + 1
        km.step()

    # Kolekcja przeżałych (wiek < max_age, jeszcze żyją)
    survivors = sorted(
        [a for a in km.atoms if a.get('topic') == 'session'],
        key=lambda x: x['T'], reverse=True
    )

    # Rdzeń następnej generacji = top-k po T
    top_vecs = [a['S'] for a in survivors[:top_k]]
    if top_vecs:
        next_core = np.sum(top_vecs, axis=0)
        next_core /= np.linalg.norm(next_core)
    else:
        next_core = core_vec  # fallback

    # Sprawdź sim rdzenia G(n+1) ze wszystkimi atomami
    next_core_sims = {}
    for atom_id, text, ckws, mkws in atoms:
        v = make_vec(ckws, mkws, dim=dim)
        next_core_sims[atom_id] = round(float(np.dot(v, next_core)), 4)

    result = {
        'gen':           gen_id,
        'admitted':      admitted,
        'rejected':      rejected,
        'survivors':     [(a['label'], round(a['T'], 3)) for a in survivors],
        'top_k':         [a['label'] for a in survivors[:top_k]],
        'top_k_T':       [round(a['T'], 3) for a in survivors[:top_k]],
        'bottom_T':      round(survivors[-1]['T'], 3) if survivors else 0,
        'next_core':     next_core,
        'next_core_sims': next_core_sims,
        'gate':          round(gate, 4),
        'n_survivors':   len(survivors),
    }

    if verbose:
        rej_ids = [r[0] for r in rejected]
        print(f"\nG{gen_id} | max_age={max_age} | gate={gate:.4f}")
        print(f"  Admitted:  {len(admitted)}/{len(atoms)}  "
              f"Rejected: {rej_ids if rej_ids else '—'}")
        print(f"  Survived:  {result['n_survivors']}")
        print(f"  Top-{top_k} → G{gen_id+1} core:")
        for label, T in zip(result['top_k'], result['top_k_T']):
            text = next((a[1] for a in atoms if a[0] == label), '')
            print(f"    [{label}] T={T}  {text[:60]}")
        if result['n_survivors'] > top_k:
            print(f"  Bottom survivor T={result['bottom_T']}")

    return result


# ============================================================
# Kolonia
# ============================================================

def run_colony(
    n_generations: int = 5,
    max_age:       int = 50,
    top_k:         int = 5,
    verbose:       bool = True,
) -> list:

    print("=" * 70)
    print("BUBBLE COLONY — ZADANIE C: SYNTEZA SESJI BADAWCZEJ")
    print("=" * 70)
    print(f"  max_age={max_age} epok/pokolenie | top_k={top_k} | "
          f"{n_generations} generacji")
    print(f"  Cykl: iniekcja → T-competition ({max_age-1} epok) → "
          f"kolekcja top-{top_k} → rozpad → next core")
    print(f"  Atomów zadania: {len(SESSION_ATOMS)}")

    # G0 rdzeń: abstrakcyjna publikowalność
    g0_core = make_core_from_kws(
        ['publishable', 'novel', 'empirical',
         'evidence', 'clear', 'formal', 'verified']
    )

    current_core = g0_core
    history      = []

    for gen in range(n_generations):
        result = run_generation(
            core_vec  = current_core,
            atoms     = SESSION_ATOMS,
            gen_id    = gen,
            max_age   = max_age,
            top_k     = top_k,
            verbose   = verbose,
        )
        history.append(result)
        current_core = result['next_core']

        # Sprawdź konwergencję (top-k identyczne jak w poprzedniej generacji)
        if gen > 0 and set(result['top_k']) == set(history[-2]['top_k']):
            print(f"\n  → Top-{top_k} stabilny w G{gen} = konwergencja kolonii")
            break

    # Podsumowanie
    print("\n" + "=" * 70)
    print("EWOLUCJA KOLONII")
    print("=" * 70)
    for h in history:
        rej = [r[0] for r in h['rejected']]
        print(f"\n  G{h['gen']}: {h['top_k']}")
        print(f"         T:  {h['top_k_T']}")
        if rej:
            print(f"         Odrzucone: {rej}")

    # Stabilny rdzeń: atomy w top-k we wszystkich generacjach
    if len(history) > 1:
        stable = set(history[0]['top_k'])
        for h in history[1:]:
            stable &= set(h['top_k'])
        print(f"\n  Stabilne przez wszystkie G: {sorted(stable)}")

    # Opis stabilnych atomów
    print("\n  STABILNE ATOMY — TEZA ARTYKUŁU:")
    stable_ids = set(history[0]['top_k'])
    for h in history[1:]:
        stable_ids &= set(h['top_k'])
    for atom_id in sorted(stable_ids):
        text = next((a[1] for a in SESSION_ATOMS if a[0] == atom_id), '')
        print(f"    [{atom_id}] {text}")

    return history


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    history = run_colony(
        n_generations = 5,
        max_age       = 50,
        top_k         = 5,
        verbose       = True,
    )

    print("\n" + "=" * 70)
    print("RÓWNANIE CYKLU ŻYCIA BAŃKI")
    print("=" * 70)
    print(f"  Czas życia bańki:    max_age = 50 epok  (deterministyczny)")
    print(f"  Czas T-competition:  max_age - 1 = 49 epok")
    print(f"  Rozpad:              epoka 50 → vacuum, 100% atomów sesji")
    print(f"  Dziedziczenie:       top-{5} po T → rdzeń następnej generacji")
    print(f"  Konwergencja:        gdy top-k stabilny między pokoleniami")
    print()
    print("  Analogia komórkowa:")
    print("  G0 = komórka macierzysta (szeroki rdzeń)")
    print("  G1 = progenitor (rdzeń z empirycznych wyników)")
    print("  G2+ = zróżnicowana (specjalizacja do tezy)")
    print()
    print("  Bańka nie umiera z braku energii.")
    print("  Bańka umiera bo wyczerpał się jej czas — max_age.")
    print("  Wynik przekazuje dalej, nie artefakt.")
