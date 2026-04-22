"""
KarmazynMatrix v3.1
VSA Attractor Dynamics in High-Dimensional Space

Changes from v3.0:
  - Weighted trace: T_i * S_i instead of equal-weight superposition
  - Energy function E = -sum(T_i * <S_i, Trace>)
  - Sieve of Eratosthenes for prime generation (O(n log log n) vs O(n^2))
  - Per-epoch metrics logging (energy, similarity distributions, atom count)
  - Honest docstring: removed "OS" framing, uses dynamical systems language
  - embed_math() arbitrariness acknowledged in comments
"""

import numpy as np
import hashlib
import math
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def sieve_of_eratosthenes(n: int) -> list[int]:
    """Return first n prime numbers using Sieve of Eratosthenes.
    O(k log log k) where k ~ n * ln(n).  Much faster than trial division.
    """
    # Upper bound via prime number theorem: p_n ~ n * ln(n) * 1.2 (safe margin)
    limit = max(30, int(n * math.log(n) * 1.3) + 10)
    sieve = bytearray([1]) * (limit + 1)
    sieve[0] = sieve[1] = 0
    for i in range(2, int(limit**0.5) + 1):
        if sieve[i]:
            sieve[i*i::i] = bytearray(len(sieve[i*i::i]))
    primes = [i for i, v in enumerate(sieve) if v]
    # If estimate was too low, extend (rare edge case)
    while len(primes) < n:
        limit *= 2
        sieve = bytearray([1]) * (limit + 1)
        sieve[0] = sieve[1] = 0
        for i in range(2, int(limit**0.5) + 1):
            if sieve[i]:
                sieve[i*i::i] = bytearray(len(sieve[i*i::i]))
        primes = [i for i, v in enumerate(sieve) if v]
    return primes[:n]


# ---------------------------------------------------------------------------
# Metrics snapshot
# ---------------------------------------------------------------------------

@dataclass
class EpochMetrics:
    epoch: int
    atom_count: int
    energy: float
    mean_similarity: float
    std_similarity: float
    min_similarity: float
    max_similarity: float
    temperatures: list[float] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)

    def __str__(self):
        temp_str = ", ".join(
            f"{lbl}:{t:.3f}" for lbl, t in zip(self.labels, self.temperatures)
        )
        return (
            f"Epoch {self.epoch:3d} | atoms={self.atom_count} | "
            f"E={self.energy:.4f} | "
            f"sim μ={self.mean_similarity:.4f} σ={self.std_similarity:.4f} "
            f"[{self.min_similarity:.4f},{self.max_similarity:.4f}] | "
            f"[{temp_str}]"
        )


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class KarmazynMatrix:
    """
    Temperature-modulated attractor dynamics in a VSA vector field.

    Each 'atom' is a unit vector S_i in R^dim with an associated scalar
    temperature T_i > 0.  The system evolves by:

        decay:     T_i <- T_i * exp(-lambda)
        resonance: T_i <- T_i + k * <S_i, Trace> - friction
        vacuum:    remove atom if T_i < vac_threshold
        trace:     Trace = normalize( sum_i  T_i * S_i )   [weighted]

    The weighted trace makes high-temperature atoms disproportionately
    influence the attractor direction, which is consistent with the
    temperature-as-salience interpretation.

    Energy functional (analogous to Lyapunov candidate):
        E(t) = -sum_i  T_i * <S_i, Trace(t)>

    Monotonicity of E is not guaranteed analytically but can be monitored
    empirically via the metrics log.
    """

    def __init__(
        self,
        dim: int = 4096,
        lambd: float = 0.08,
        vac_threshold: float = 0.15,
        k: float = 0.2,
        friction: float = 0.02,
        seed: int = 42,
    ):
        self.dim = dim
        self.lambd = lambd
        self.vac_threshold = vac_threshold
        self.k = k
        self.friction = friction
        self.rng_seed = seed
        self.atoms: list[dict] = []
        self.trace = np.zeros(dim)
        self.time = 0
        self.metrics_log: list[EpochMetrics] = []

        # Precompute primes once at init (O(dim log log dim))
        self._primes: Optional[list[int]] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _normalize(self, v: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(v)
        return v / (norm + 1e-9)

    def _get_primes(self) -> list[int]:
        if self._primes is None:
            self._primes = sieve_of_eratosthenes(self.dim)
        return self._primes

    # ------------------------------------------------------------------
    # VSA operations (HRR standard)
    # ------------------------------------------------------------------

    def bind(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """Circular convolution binding (HRR).  bind(a,b) encodes relation a*b."""
        return np.fft.ifft(np.fft.fft(a) * np.fft.fft(b)).real

    def unbind(self, h: np.ndarray, a: np.ndarray) -> np.ndarray:
        """Approximate unbinding via circular correlation.  unbind(bind(a,b), a) ≈ b."""
        return np.fft.ifft(np.fft.fft(h) * np.conj(np.fft.fft(a))).real

    # ------------------------------------------------------------------
    # Embeddings
    # NOTE: Mathematical embeddings (embed_math) use deterministic functions
    # chosen for geometric diversity, NOT for semantic grounding.
    # The labels ("miłość", "uczciwość", …) are illustrative; any label
    # could be swapped with another without changing system behaviour.
    # This must be stated explicitly in any publication.
    # ------------------------------------------------------------------

    def embed_linguistic(self, text: str) -> np.ndarray:
        h = hashlib.md5(text.encode("utf-8")).hexdigest()
        seed = int(h, 16) % (2**32)
        gen = np.random.default_rng(seed)
        v = gen.normal(0, 1.0, self.dim)
        return self._normalize(v)

    def embed_math(self, concept: str) -> np.ndarray:
        """
        Returns a unit vector whose *structure* is defined by a mathematical
        sequence.  The mapping concept->sequence is arbitrary and chosen only
        to produce vectors with distinct spectral / distributional properties.

        For publication: cite this as 'structured seed vectors with diverse
        geometric properties' rather than 'semantically meaningful embeddings'.
        """
        v = np.zeros(self.dim, dtype=np.float64)
        if concept == "miłość":
            # Exponential growth -> high-energy asymmetric vector
            v = np.array([math.exp(i / self.dim) for i in range(self.dim)])
        elif concept == "uczciwość":
            # Constant -> projects equally on all directions
            v = np.ones(self.dim)
        elif concept == "autentyczność":
            # Prime sequence -> irregular, low autocorrelation
            v = np.array(self._get_primes(), dtype=np.float64)
        elif concept == "szacunek":
            # Quasiperiodic (golden ratio) -> dense in [0,1], low discrepancy
            phi = (1 + math.sqrt(5)) / 2
            v = np.array([(phi * i) % 1.0 for i in range(self.dim)])
        elif concept == "ład":
            # Sinusoidal -> concentrated energy in narrow frequency band
            x = np.linspace(0, 2 * np.pi, self.dim)
            v = np.sin(x)
        else:
            raise ValueError(f"Unknown math concept: {concept!r}")
        return self._normalize(v.astype(np.float64))

    # ------------------------------------------------------------------
    # Atom management
    # ------------------------------------------------------------------

    def add_atom(self, label: str, topic: str, init_T: float = 1.0, is_math: bool = False) -> None:
        vector = self.embed_math(label) if is_math else self.embed_linguistic(label)
        self.atoms.append({"label": label, "topic": topic, "S": vector, "T": init_T})
        self._rebuild_trace()

    # ------------------------------------------------------------------
    # Core dynamics
    # ------------------------------------------------------------------

    def _rebuild_trace(self) -> None:
        """
        Weighted trace: high-temperature atoms dominate attractor direction.
        FIX from v3.0: was unweighted normalize(sum(S_i)).
        """
        if not self.atoms:
            self.trace = np.zeros(self.dim)
            return
        # T_i * S_i — temperature as salience weight
        weighted_sum = np.sum([a["T"] * a["S"] for a in self.atoms], axis=0)
        self.trace = self._normalize(weighted_sum)

    def energy(self) -> float:
        """
        Energy functional: E = -sum_i T_i * <S_i, Trace>.
        Lower (more negative) = more coherent, higher alignment.
        Analogous to a Lyapunov candidate; monotonicity should be
        verified empirically across seeds.
        """
        if not self.atoms:
            return 0.0
        return -sum(a["T"] * float(np.dot(a["S"], self.trace)) for a in self.atoms)

    def measure_influence(self, atom_S: np.ndarray) -> float:
        return float(np.dot(atom_S, self.trace))

    def step(self) -> None:
        self.time += 1
        alive = []
        for a in self.atoms:
            # 1. Decay
            a["T"] *= math.exp(-self.lambd)
            # 2. Resonance with friction gate
            infl = self.measure_influence(a["S"])
            a["T"] += (self.k * infl) - self.friction
            if a["T"] >= self.vac_threshold:
                alive.append(a)
        self.atoms = alive
        self._rebuild_trace()

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def collect_metrics(self) -> EpochMetrics:
        """Snapshot current state into an EpochMetrics object."""
        sims = [self.measure_influence(a["S"]) for a in self.atoms] if self.atoms else [0.0]
        sims_arr = np.array(sims)
        m = EpochMetrics(
            epoch=self.time,
            atom_count=len(self.atoms),
            energy=self.energy(),
            mean_similarity=float(sims_arr.mean()),
            std_similarity=float(sims_arr.std()),
            min_similarity=float(sims_arr.min()),
            max_similarity=float(sims_arr.max()),
            temperatures=[round(a["T"], 4) for a in self.atoms],
            labels=[a["label"] for a in self.atoms],
        )
        self.metrics_log.append(m)
        return m


# ---------------------------------------------------------------------------
# Reproducing test (identical setup to v3.0 for comparability)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("KarmazynMatrix v3.1 — reproducing test (seed=42, dim=4096)")
    print("=" * 70)

    m = KarmazynMatrix(dim=4096, friction=0.02)

    # Core atoms (structured seed vectors)
    m.add_atom("miłość",     "rdzeń",     init_T=2.5, is_math=True)
    m.add_atom("uczciwość",  "rdzeń",     init_T=2.0, is_math=True)
    m.add_atom("szacunek",   "rdzeń",     init_T=2.0, is_math=True)

    # Anomaly injections
    m.add_atom("ład",         "anomalia",  init_T=1.0, is_math=True)   # sinusoid
    m.add_atom("wirus_agresor", "destrukcja", init_T=1.5, is_math=False)

    print(f"Start: {m.dim}D | {len(m.atoms)} atoms\n")

    prev_energy = None
    energy_violations = 0  # count epochs where E increases (non-monotone)

    for e in range(1, 101):
        m.step()
        metrics = m.collect_metrics()

        if e % 10 == 0:
            print(metrics)

        # Track energy monotonicity
        if prev_energy is not None and metrics.energy > prev_energy:
            energy_violations += 1
        prev_energy = metrics.energy

    print("\n" + "=" * 70)
    print(f"Energy monotonicity violations: {energy_violations}/100 epochs")
    print(f"Final atom count: {m.atoms and len(m.atoms) or 0}")
    print(f"Final energy: {m.metrics_log[-1].energy:.6f}")

    # Similarity distribution summary
    all_sims = []
    for mx in m.metrics_log:
        for a in m.atoms:
            all_sims.append(m.measure_influence(a["S"]))
    print(f"\nFinal similarity stats (last epoch):")
    print(f"  μ={m.metrics_log[-1].mean_similarity:.4f}  "
          f"σ={m.metrics_log[-1].std_similarity:.4f}  "
          f"range=[{m.metrics_log[-1].min_similarity:.4f}, "
          f"{m.metrics_log[-1].max_similarity:.4f}]")
