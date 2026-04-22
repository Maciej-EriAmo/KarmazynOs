"""
HSS Protocol v0.1 — Holographic Session Space
Geometryczna przestrzeń komunikacji agentów bez wspólnej ontologii

Architektura:
    Agent_i = (Core_i [stały], Trace_i [dynamiczny])
    H       = anonimowe pole emisji
    message = warm atom: sim(msg, Trace_sender) = emission_sim

Kluczowe właściwości:
    - Routing przez geometrię: wiadomość dociera do agentów z podobnym Trace
    - Brak adresów, brak protokołu, brak wspólnego słownika
    - Agent NIE odbiera własnych emisji
    - Populacja w równowadze: ~core + local_plateau + H_plateau

Tabela zasięgu (dim=4096, gate=0.1537):
    emission_sim 0.16 -> zasięg > core_overlap 0.95  (szept)
    emission_sim 0.20 -> zasięg > core_overlap 0.80  (bliscy)
    emission_sim 0.30 -> zasięg > core_overlap 0.55  (normalny)
    emission_sim 0.50 -> zasięg > core_overlap 0.35  (głośny)
    emission_sim 0.70 -> zasięg > core_overlap 0.25  (broadcast)
"""

import numpy as np
import math
from dataclasses import dataclass, field
from typing import Optional
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from karmazyn_matrix_v34 import KarmazynMatrix


# ===========================================================================
# Pole emisji
# ===========================================================================

@dataclass
class Emission:
    vector:  np.ndarray
    emitter: str   # ID nadawcy — do filtrowania własnych emisji
    age:     int = 0


class HolographicField:
    """
    Anonimowe pole emisji H.
    Atomy wygasają po max_age epokach.
    Agent nie odbiera własnych emisji.
    """

    def __init__(self, max_age: int = 20):
        self.max_age = max_age
        self.atoms: list[Emission] = []

    def emit(self, vector: np.ndarray, emitter: str) -> None:
        v = vector / (np.linalg.norm(vector) + 1e-9)
        self.atoms.append(Emission(vector=v, emitter=emitter))

    def step(self) -> None:
        for a in self.atoms:
            a.age += 1
        self.atoms = [a for a in self.atoms if a.age < self.max_age]

    def query(self, trace: np.ndarray, gate: float,
              exclude_emitter: str = "") -> list[np.ndarray]:
        return [
            a.vector for a in self.atoms
            if a.emitter != exclude_emitter
            and float(np.dot(a.vector, trace)) > gate
        ]

    def __len__(self) -> int:
        return len(self.atoms)


# ===========================================================================
# Agent
# ===========================================================================

@dataclass
class AgentMetrics:
    epoch:          int
    population:     int
    core_sim:       float
    recv_from_H:    int
    local_admitted: int
    emitted:        int
    field_size:     int


class HSSAgent:
    """
    Agent w przestrzeni HSS.

    Core — stały, definiuje tożsamość.
    Trace — dynamiczny, ewoluuje przez lokalne atomy + odebrane z H.
    Gate — (lambda*tau + f)/k — identyczny z warunkiem przeżycia KM.
    """

    def __init__(
        self,
        name:              str,
        core_vector:       np.ndarray,
        dim:               int   = 4096,
        emission_sim:      float = 0.30,
        emission_interval: int   = 5,
        max_age:           int   = 30,
        p_signal:          float = 0.20,
        km_seed:           int   = 42,
        stream_seed:       int   = 99,
    ):
        self.name              = name
        self.dim               = dim
        self.emission_sim      = emission_sim
        self.emission_interval = emission_interval
        self.max_age           = max_age
        self.p_signal          = p_signal

        self.km   = KarmazynMatrix(dim=dim, seed=km_seed)
        self._core = core_vector / np.linalg.norm(core_vector)

        self.km.add_atom_vector(f"{name}_core", "core", self._core, init_T=2.5)
        self.km.atoms[-1]["permanent"] = True
        self.km.atoms[-1]["age"]       = 0

        self.gate = (self.km.lambd * self.km.vac_threshold
                     + self.km.friction) / self.km.k

        self._stream_rng = np.random.default_rng(stream_seed)
        self._emit_rng   = np.random.default_rng(stream_seed + 1000)
        self._counter    = 0
        self._epoch      = 0
        self.metrics_log: list[AgentMetrics] = []

    @property
    def core(self)  -> np.ndarray: return self._core
    @property
    def trace(self) -> np.ndarray: return self.km.trace

    def warmup(self, n: int = 30) -> None:
        for _ in range(n):
            for a in self.km.atoms:
                a["age"] = a.get("age", 0) + 1
            self.km.step()

    def step(self, field: HolographicField) -> AgentMetrics:
        self._epoch += 1

        # 1. Wygaś stare atomy
        self.km.atoms = [
            a for a in self.km.atoms
            if a.get("permanent", False) or a.get("age", 0) < self.max_age
        ]

        # 2. Odbiór z H — tylko od innych agentów
        recv_vecs = field.query(self.km.trace, self.gate,
                                exclude_emitter=self.name)
        for v in recv_vecs:
            self._counter += 1
            self.km.atoms.append({
                "label": f"{self.name}_H_{self._counter}",
                "topic": "received",
                "S": v, "T": 1.2,
                "age": 0, "permanent": False,
            })
            self.km._rebuild_trace()

        # 3. Lokalny strumień Genesis 5
        local_admitted = 0
        for _ in range(3):
            cand = self._draw_local_stream()
            if cand is not None:
                sim = float(np.dot(cand, self.km.trace))
                if sim > self.gate:
                    self._counter += 1
                    self.km.atoms.append({
                        "label": f"{self.name}_loc_{self._counter}",
                        "topic": "local",
                        "S": cand, "T": 1.5,
                        "age": 0, "permanent": False,
                    })
                    self.km._rebuild_trace()
                    local_admitted += 1

        # 4. Wiek++
        for a in self.km.atoms:
            a["age"] = a.get("age", 0) + 1

        # 5. Dynamika KM
        self.km.step()

        # 6. Emisja do H
        emitted = 0
        if self._epoch % self.emission_interval == 0:
            msg = self._generate_emission()
            if msg is not None:
                field.emit(msg, emitter=self.name)
                emitted = 1

        core_sim = float(np.dot(self._core, self.km.trace))
        m = AgentMetrics(
            epoch=self._epoch,
            population=len(self.km.atoms),
            core_sim=core_sim,
            recv_from_H=len(recv_vecs),
            local_admitted=local_admitted,
            emitted=emitted,
            field_size=len(field),
        )
        self.metrics_log.append(m)
        return m

    def _generate_emission(self) -> Optional[np.ndarray]:
        noise = self._emit_rng.normal(0, 1, self.dim)
        perp  = noise - np.dot(noise, self.km.trace) * self.km.trace
        if np.linalg.norm(perp) < 1e-9:
            return None
        perp /= np.linalg.norm(perp)
        msg = (self.emission_sim * self.km.trace
               + math.sqrt(1 - self.emission_sim**2) * perp)
        return msg / np.linalg.norm(msg)

    def _draw_local_stream(self) -> Optional[np.ndarray]:
        is_signal = self._stream_rng.random() < self.p_signal
        if is_signal:
            noise = self._stream_rng.normal(0, 1, self.dim)
            perp  = noise - np.dot(noise, self._core) * self._core
            if np.linalg.norm(perp) < 1e-9:
                return None
            perp /= np.linalg.norm(perp)
            cand = math.sqrt(1 - 0.16) * self._core + 0.4 * perp
        else:
            cand = self._stream_rng.normal(0, 1, self.dim)
        return cand / np.linalg.norm(cand)


# ===========================================================================
# Helpers
# ===========================================================================

def make_core(seed: int, dim: int = 4096) -> np.ndarray:
    v = np.random.default_rng(seed).normal(0, 1, dim)
    return v / np.linalg.norm(v)


def make_aligned_core(base: np.ndarray, sim_target: float,
                      seed: int, dim: int = 4096) -> np.ndarray:
    rng  = np.random.default_rng(seed)
    n    = rng.normal(0, 1, dim)
    perp = n - np.dot(n, base) * base
    perp /= np.linalg.norm(perp)
    v    = sim_target * base + math.sqrt(1 - sim_target**2) * perp
    return v / np.linalg.norm(v)


# ===========================================================================
# Eksperyment 1: 3 agenty
# ===========================================================================

def run_experiment(verbose: bool = True) -> dict:
    """
    Alpha, Beta (bliski Alpha, overlap=0.80), Gamma (odległy, overlap=0.20).
    emission_sim=0.30 -> zasięg > 0.55.
    Predykcja: Alpha <-> Beta: wysoka wymiana. Alpha/Beta <-> Gamma: niska.
    """
    dim = 4096
    core_alpha = make_core(1, dim)
    core_beta  = make_aligned_core(core_alpha, 0.80, seed=2, dim=dim)
    core_gamma = make_aligned_core(core_alpha, 0.20, seed=3, dim=dim)

    ov_ab = float(np.dot(core_alpha, core_beta))
    ov_ag = float(np.dot(core_alpha, core_gamma))
    ov_bg = float(np.dot(core_beta,  core_gamma))

    if verbose:
        print("\n" + "="*70)
        print("EKSPERYMENT 1: 3 agenty, emission_sim=0.30, 100 epok")
        print("="*70)
        print(f"\n  Core overlaps:")
        print(f"    Alpha-Beta:  {ov_ab:.3f}  > 0.55  wymiana: TAK (predykcja)")
        print(f"    Alpha-Gamma: {ov_ag:.3f}  < 0.55  wymiana: NIE (predykcja)")
        print(f"    Beta-Gamma:  {ov_bg:.3f}  < 0.55  wymiana: NIE (predykcja)")

    field = HolographicField(max_age=20)
    alpha = HSSAgent("Alpha", core_alpha, km_seed=42, stream_seed=100)
    beta  = HSSAgent("Beta",  core_beta,  km_seed=43, stream_seed=200)
    gamma = HSSAgent("Gamma", core_gamma, km_seed=44, stream_seed=300)

    for ag in [alpha, beta, gamma]:
        ag.warmup(30)

    if verbose:
        print(f"\n  {'ep':>4} | {'|H|':>4} | "
              f"{'α pop':>6} {'β pop':>6} {'γ pop':>6} | "
              f"{'α csim':>7} {'β csim':>7} {'γ csim':>7} | "
              f"{'α←H':>4} {'β←H':>4} {'γ←H':>4}")
        print("  " + "-"*82)

    for ep in range(100):
        field.step()
        ma = alpha.step(field)
        mb = beta.step(field)
        mg = gamma.step(field)
        if verbose and (ep + 1) % 20 == 0:
            print(f"  {ep+1:4d} | {len(field):4d} | "
                  f"{ma.population:6d} {mb.population:6d} {mg.population:6d} | "
                  f"{ma.core_sim:7.4f} {mb.core_sim:7.4f} {mg.core_sim:7.4f} | "
                  f"{ma.recv_from_H:4d} {mb.recv_from_H:4d} {mg.recv_from_H:4d}")

    tot = {
        "alpha": sum(m.recv_from_H for m in alpha.metrics_log),
        "beta":  sum(m.recv_from_H for m in beta.metrics_log),
        "gamma": sum(m.recv_from_H for m in gamma.metrics_log),
    }
    t_ab = float(np.dot(alpha.km.trace, beta.km.trace))
    t_ag = float(np.dot(alpha.km.trace, gamma.km.trace))

    if verbose:
        print(f"\n  Łączne odbiory z H:")
        print(f"    Alpha: {tot['alpha']:4d}  Beta: {tot['beta']:4d}  Gamma: {tot['gamma']:4d}")
        print(f"  Trace alignment końcowy:")
        print(f"    sim(Trace_α, Trace_β) = {t_ab:.4f}  [bliskie trace → wzajemne widzenie]")
        print(f"    sim(Trace_α, Trace_γ) = {t_ag:.4f}  [różne trace → brak widzenia]")
        routing_ok = tot["beta"] > tot["gamma"] * 1.5
        print(f"\n  Routing geometryczny: {'✓ DZIAŁA' if routing_ok else '✗ WYMAGA ANALIZY'}")
        print(f"    Beta/Gamma odbiory ratio: {tot['beta']}/{tot['gamma']} = "
              f"{tot['beta']/max(1,tot['gamma']):.1f}x")

    return {"tot": tot, "ov_ab": ov_ab, "ov_ag": ov_ag,
            "t_ab": t_ab, "t_ag": t_ag}


# ===========================================================================
# Eksperyment 2: sweep core_overlap vs odbiory
# ===========================================================================

def run_routing_sweep(verbose: bool = True) -> dict:
    if verbose:
        print("\n" + "="*70)
        print("EKSPERYMENT 2: core_overlap → odbiory (50 epok)")
        print("="*70)

    dim        = 4096
    core_alpha = make_core(1, dim)
    results    = {}

    for overlap in [1.0, 0.90, 0.80, 0.70, 0.60, 0.50, 0.40, 0.30, 0.20, 0.10]:
        field = HolographicField(max_age=20)
        if overlap == 1.0:
            core_B = core_alpha.copy()
        else:
            core_B = make_aligned_core(core_alpha, overlap,
                                       seed=int(overlap * 100) + 7, dim=dim)

        emitter  = HSSAgent("E", core_alpha, emission_sim=0.30,
                             emission_interval=3, km_seed=42, stream_seed=10)
        receiver = HSSAgent("R", core_B, emission_sim=0.30,
                             emission_interval=10000, km_seed=43, stream_seed=20)
        emitter.warmup(20)
        receiver.warmup(20)

        for _ in range(50):
            field.step()
            emitter.step(field)
            receiver.step(field)

        total = sum(m.recv_from_H for m in receiver.metrics_log)
        results[overlap] = total

        if verbose:
            filled = min(total // 2, 25)
            bar    = "█" * filled + "░" * (25 - filled)
            status = "routes" if total > 0 else "silent"
            print(f"  overlap={overlap:.2f} | recv={total:4d} | {bar} | {status}")

    return results


# ===========================================================================
# Main
# ===========================================================================

if __name__ == "__main__":
    print("HSS Protocol v0.1")
    print("Geometryczna przestrzeń komunikacji agentów")
    print("Brak adresów · Brak protokołu · Brak wspólnej ontologii")
    print()
    print(f"  Gate threshold: {KarmazynMatrix().gate_threshold:.4f}"
          if hasattr(KarmazynMatrix(), 'gate_threshold')
          else f"  Gate: (λτ+f)/k = {(0.08*0.15+0.01875)/0.2:.4f}")
    print(f"  dim=4096  |  emission_sim=0.30  |  routing_crossover≈0.55")

    sweep   = run_routing_sweep(verbose=True)
    results = run_experiment(verbose=True)

    print("\n" + "="*70)
    print("PODSUMOWANIE")
    print("="*70)
    print(f"  Routing crossover (sweep):  overlap ~0.55–0.60")
    print(f"  Alpha-Beta (0.80):          {results['tot']['beta']} odbiory")
    print(f"  Alpha-Gamma (0.20):         {results['tot']['gamma']} odbiory")
    print(f"  Ratio Beta/Gamma:           "
          f"{results['tot']['beta']/max(1,results['tot']['gamma']):.1f}x")
    print(f"  Trace konwergencja α-β:     {results['t_ab']:.4f}")
    print(f"  Trace dywergencja α-γ:      {results['t_ag']:.4f}")
    print()
    print("  Widoczność = funkcja lokalnej zgodności geometrycznej.")
    print("  Brak protokołu. Brak wspólnego słownika. Tylko geometria.")
