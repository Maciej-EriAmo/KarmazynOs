"""
Agent Roboczy w Bańce HSS
Zadanie C: Synteza sesji badawczej — co jest publikowalne i dlaczego

Architektura:
    1. LLM (Groq) dekomponuje sesję na atomy tekstowe
    2. Atomy wchodzą jako strumień do agenta HSS
    3. Agent iteruje — selekcja geometryczna przez Trace
    4. LLM czyta przeżałe atomy i syntezuje wniosek
    5. Log: co przeżyło, co odpadło, dlaczego (przez sim)

Rdzeń agenta: "co jest publikowalne: nowość + dowód empiryczny + jasność"
"""

import numpy as np
import math
import json
import sys
import os
import hashlib
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from karmazyn_matrix_v34 import KarmazynMatrix

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# ===========================================================================
# Embedding tekstu -> wektor VSA
# ===========================================================================

def embed_text(text: str, dim: int = 4096) -> np.ndarray:
    """
    Deterministyczny embedding tekstu przez MD5 seed.
    Każde unikalne zdanie -> unikalny pseudolosowy wektor jednostkowy.
    Bliskość semantyczna nie jest tu zachowana — ale spójność tematyczna
    wyłania się przez wspólny rdzeń agenta.
    """
    h    = hashlib.md5(text.encode("utf-8")).hexdigest()
    seed = int(h, 16) % (2**32)
    rng  = np.random.default_rng(seed)
    v    = rng.normal(0, 1, dim)
    return v / np.linalg.norm(v)


def embed_concept(concept: str, keywords: list[str], dim: int = 4096) -> np.ndarray:
    """
    Embedding konceptu jako superpozycja wektorów kluczowych słów.
    Koncepty dzielące słowa kluczowe będą miały wyższe sim.
    """
    vectors = [embed_text(kw, dim) for kw in keywords]
    combined = np.sum(vectors, axis=0)
    return combined / np.linalg.norm(combined)


# ===========================================================================
# Atomy sesji — ręczna dekompozycja
# ===========================================================================

SESSION_ATOMS = [
    # --- Wyniki empiryczne z kodem ---
    {
        "id": "E1",
        "text": "Adaptive friction f=c/sqrt(d) eliminuje hiperparametr zależny od wymiaru. Geometric derivation: próg = 1.2x oczekiwane random similarity.",
        "category": "empirical",
        "keywords": ["adaptive", "friction", "dimension", "geometric", "derivation", "threshold"],
        "novelty": "high", "evidence": "high", "clarity": "high"
    },
    {
        "id": "E2",
        "text": "Warunek przeżycia k*sim > lambda*tau + f — analityczny próg separacji. sim_min=0.1537, separation margin 884%. Formalnie wyprowadzony.",
        "category": "empirical",
        "keywords": ["survival", "condition", "threshold", "separation", "formal", "derived"],
        "novelty": "high", "evidence": "high", "clarity": "high"
    },
    {
        "id": "E3",
        "text": "Baseline SNR 20-150x wyższy niż static HRR i Random Walk. Random walk = taki sam jak HRR — geometria, nie temperatura, robi robotę.",
        "category": "empirical",
        "keywords": ["baseline", "SNR", "comparison", "geometry", "selection", "noise"],
        "novelty": "high", "evidence": "high", "clarity": "high"
    },
    {
        "id": "E4",
        "text": "Embedding ablation: structured 0.9615 vs aligned-random 0.9425. Różnica 0.019 = efekt spójności klastra, nie sekwencji matematycznych. Arbitrary mapping potwierdzony.",
        "category": "empirical",
        "keywords": ["ablation", "cluster", "arbitrary", "embedding", "confirmed", "experimental"],
        "novelty": "medium", "evidence": "high", "clarity": "high"
    },
    {
        "id": "E5",
        "text": "Energy/coherence monotonicity 100% seedów post-epoch 20. 50 seedów, zero naruszeń po epoce 20. Empiryczny kandydat Lyapunova.",
        "category": "empirical",
        "keywords": ["energy", "monotonicity", "seeds", "statistical", "Lyapunov", "empirical"],
        "novelty": "medium", "evidence": "high", "clarity": "high"
    },
    {
        "id": "E6",
        "text": "Hopfield benchmark 3 zadania: Task1 labelled retrieval Hopfield wygrywa (0.9999 vs 0.9884). Task2 unsupervised discovery KM wygrywa (1.000 vs 0.999). Task3 online SNR KM wygrywa 30x.",
        "category": "empirical",
        "keywords": ["Hopfield", "benchmark", "comparison", "unsupervised", "retrieval", "SNR"],
        "novelty": "high", "evidence": "high", "clarity": "high"
    },
    {
        "id": "E7",
        "text": "HSS routing formula: core_overlap > gate/emission_sim. Crossover 0.512 dla emission_sim=0.30. Potwierdzony sweepem. Routing binarny — między 0.50 a 0.40 ostry skok do zera.",
        "category": "empirical",
        "keywords": ["routing", "formula", "overlap", "crossover", "binary", "verified"],
        "novelty": "high", "evidence": "high", "clarity": "high"
    },
    {
        "id": "E8",
        "text": "Gamma 0 odbiorów przez 100 epok przy core_overlap=0.20. Izolacja jako naturalny stan spoczynkowy. Core_sim=0.997 bez interwencji.",
        "category": "empirical",
        "keywords": ["isolation", "natural", "zero", "reception", "identity", "preserved"],
        "novelty": "medium", "evidence": "high", "clarity": "high"
    },
    # --- Genesis 5 ---
    {
        "id": "G1",
        "text": "E2 ontologiczna odporność: 0 wrogich atomów wpuszczonych przy nagłym ataku ortogonalnym. Core_sim poprawia się do 0.9615 gdy stare atomy wygasają.",
        "category": "genesis5",
        "keywords": ["immunity", "hostile", "sudden", "orthogonal", "zero", "attack"],
        "novelty": "high", "evidence": "high", "clarity": "high"
    },
    {
        "id": "G2",
        "text": "E3 adaptacja do dryftu: korelacja strumień-trace 0.9457 przy stopniowej rotacji. Trace podąża za środowiskiem ciągłym.",
        "category": "genesis5",
        "keywords": ["drift", "adaptation", "correlation", "gradual", "environment", "follow"],
        "novelty": "high", "evidence": "high", "clarity": "high"
    },
    {
        "id": "G3",
        "text": "Asymetria E2/E3: nagłe zmiany blokowane, ciągłe śledzone. Jeden próg tworzy dwie różne odpowiedzi na dwie topologie zmian wejściowych.",
        "category": "genesis5",
        "keywords": ["asymmetry", "sudden", "gradual", "topology", "single", "threshold"],
        "novelty": "high", "evidence": "high", "clarity": "high"
    },
    {
        "id": "G4",
        "text": "Observer-dependent representation: Trace = f(historia strumienia, filtr). Nie model danych — path-dependent projection operator.",
        "category": "genesis5",
        "keywords": ["observer", "dependent", "representation", "history", "path", "projection"],
        "novelty": "high", "evidence": "medium", "clarity": "medium"
    },
    {
        "id": "G5",
        "text": "Populacja w równowadze 27.5 +/- 3.66 atomów. Bounded, not exploding. Trace drift 0.000184/epokę — quasi-statyczny, nie zamrożony.",
        "category": "genesis5",
        "keywords": ["equilibrium", "bounded", "population", "drift", "quasi-static"],
        "novelty": "low", "evidence": "high", "clarity": "high"
    },
    # --- Teoria ---
    {
        "id": "T1",
        "text": "System klasy: temperature-gated mean-field attractor. Analogia do replicator dynamics — fitness = alignment z polem populacji.",
        "category": "theory",
        "keywords": ["mean-field", "replicator", "dynamics", "class", "attractor", "temperature"],
        "novelty": "high", "evidence": "medium", "clarity": "high"
    },
    {
        "id": "T2",
        "text": "Trace nie jest estymatorem — wybiera podprzestrzeń która może istnieć w systemie. Nie modeluje danych, definiuje admissible trajectories.",
        "category": "theory",
        "keywords": ["trace", "subspace", "admissible", "not-estimator", "selection", "defines"],
        "novelty": "high", "evidence": "medium", "clarity": "high"
    },
    {
        "id": "T3",
        "text": "bind(core, boundary) ma sim~0.98 z Trace — dwa rejestry nowości. Boundary atom 98.8% nowy, jego relacja z rdzeniem mocno zakorzeniona. Genesis 6 fundament.",
        "category": "theory",
        "keywords": ["bind", "boundary", "two-registers", "novelty", "foundation", "genesis6"],
        "novelty": "high", "evidence": "high", "clarity": "medium"
    },
    {
        "id": "T4",
        "text": "Czarna dziura / coherent jet: horyzont jako brama selekcji, jet jako strumień wejściowy. Analogia geometryczna do klasy układów. Inspiracyjna, nie dowodowa.",
        "category": "theory",
        "keywords": ["black-hole", "analogy", "horizon", "jet", "geometric", "inspirational"],
        "novelty": "medium", "evidence": "low", "clarity": "medium"
    },
    {
        "id": "T5",
        "text": "Relational survival = f(geometric alignment). Genesis 4: external relation (0.52) odpada, internal (0.98) przeżywa. Najciekawszy empiryczny insight całej pracy.",
        "category": "theory",
        "keywords": ["relational", "survival", "alignment", "genesis4", "key-insight", "empirical"],
        "novelty": "high", "evidence": "high", "clarity": "high"
    },
    # --- HSS ---
    {
        "id": "H1",
        "text": "HSS: brak adresów, brak protokołu, brak ontologii. Routing przez geometrię. Widoczność = projekcja H na lokalny Trace. System widoczności nie komunikacji.",
        "category": "hss",
        "keywords": ["no-protocol", "routing", "geometry", "visibility", "system", "minimal"],
        "novelty": "high", "evidence": "high", "clarity": "high"
    },
    {
        "id": "H2",
        "text": "emission_sim kontroluje identity vs convergence tradeoff. 0.16 -> tożsamość 0.995, 0.30 -> konwergencja 0.70. Jeden parametr, dwa reżimy.",
        "category": "hss",
        "keywords": ["emission", "identity", "convergence", "tradeoff", "single-parameter"],
        "novelty": "high", "evidence": "high", "clarity": "high"
    },
    {
        "id": "H3",
        "text": "Alpha-Beta trace convergence 0.698 przez wspólne pole. Emergentna synchronizacja bez negocjacji. Analogia do synchronizacji oscylatorów.",
        "category": "hss",
        "keywords": ["convergence", "emergent", "synchronization", "shared-attractor", "no-negotiation"],
        "novelty": "high", "evidence": "high", "clarity": "high"
    },
    {
        "id": "H4",
        "text": "Genesis 6: generacja na horyzoncie, nie z centrum. boundary = sim_min * Trace + sqrt(1-sim_min^2) * noise. Maksymalna nowość przy minimalnym koszcie wejścia.",
        "category": "hss",
        "keywords": ["genesis6", "boundary", "generation", "horizon", "maximum-novelty", "minimal-cost"],
        "novelty": "high", "evidence": "medium", "clarity": "high"
    },
]


# ===========================================================================
# Agent
# ===========================================================================

@dataclass
class WorkingAtom:
    id:       str
    text:     str
    vector:   np.ndarray
    T:        float
    age:      int = 0
    sim_log:  list = None

    def __post_init__(self):
        if self.sim_log is None:
            self.sim_log = []


class ResearchAgent:
    """
    Agent pracujący nad syntezą sesji badawczej.
    Rdzeń: 'co jest publikowalne — nowość + dowód empiryczny + jasność'
    """

    def __init__(self, dim: int = 4096, seed: int = 42):
        self.dim = dim
        self.km  = KarmazynMatrix(dim=dim, seed=seed)

        # Rdzeń: publikowalność
        core_keywords = [
            "publishable", "novel", "empirical", "evidence",
            "clear", "contribution", "reproducible", "verified"
        ]
        self._core_vec = embed_concept("publishable novel empirical evidence", core_keywords, dim)

        # Trzy stałe atomy rdzenia
        self.km.add_atom_vector("core_novelty",    "core",
            embed_concept("novel contribution new finding", ["novel","new","contribution","finding"], dim),
            init_T=2.5)
        self.km.add_atom_vector("core_evidence",   "core",
            embed_concept("empirical evidence verified reproducible", ["empirical","verified","evidence","reproducible"], dim),
            init_T=2.5)
        self.km.add_atom_vector("core_clarity",    "core",
            embed_concept("clear formal precise mathematical", ["clear","formal","precise","mathematical"], dim),
            init_T=2.5)

        for a in self.km.atoms:
            a["permanent"] = True
            a["age"]       = 0

        self.gate = (self.km.lambd * self.km.vac_threshold + self.km.friction) / self.km.k
        self._working_atoms: list[WorkingAtom] = []
        self._epoch = 0
        self._log   = []

        # Warmup
        for _ in range(20):
            for a in self.km.atoms: a["age"] = a.get("age",0) + 1
            self.km.step()

    @property
    def trace(self) -> np.ndarray:
        return self.km.trace

    def inject_session(self, atoms: list[dict], batch_size: int = 3) -> None:
        """Wstrzyknij atomy sesji jako strumień wejściowy."""
        self._session_queue = list(atoms)
        self._batch_size    = batch_size

    def step(self) -> dict:
        self._epoch += 1

        # Wygaś stare
        alive = []
        for wa in self._working_atoms:
            wa.age += 1
            if wa.age < 40:
                alive.append(wa)
            else:
                self._log.append({
                    "event": "expired", "id": wa.id,
                    "text": wa.text[:60], "final_T": round(wa.T,3),
                    "epoch": self._epoch
                })
        self._working_atoms = alive

        # Zaktualizuj km.atoms z working_atoms
        self.km.atoms = [a for a in self.km.atoms if a.get("permanent")]
        for wa in self._working_atoms:
            self.km.atoms.append({
                "label": wa.id, "topic": "session",
                "S": wa.vector, "T": wa.T,
                "age": wa.age, "permanent": False
            })
        self.km._rebuild_trace()

        # Pobierz nowe atomy ze strumienia sesji
        admitted = []
        if hasattr(self, "_session_queue") and self._session_queue:
            batch = self._session_queue[:self._batch_size]
            self._session_queue = self._session_queue[self._batch_size:]

            for atom_data in batch:
                vec = embed_text(atom_data["text"], self.dim)
                # Wzbogać wektor o słowa kluczowe
                if atom_data.get("keywords"):
                    kw_vec = embed_concept(
                        " ".join(atom_data["keywords"]),
                        atom_data["keywords"], self.dim
                    )
                    vec = 0.7 * vec + 0.3 * kw_vec
                    vec /= np.linalg.norm(vec)

                sim = float(np.dot(vec, self.km.trace))

                if sim > self.gate:
                    wa = WorkingAtom(
                        id=atom_data["id"], text=atom_data["text"],
                        vector=vec, T=1.5
                    )
                    self._working_atoms.append(wa)
                    self.km.atoms.append({
                        "label": wa.id, "topic": "session",
                        "S": wa.vector, "T": wa.T,
                        "age": 0, "permanent": False
                    })
                    self.km._rebuild_trace()
                    admitted.append(atom_data["id"])
                    self._log.append({
                        "event": "admitted", "id": atom_data["id"],
                        "sim": round(sim, 4), "epoch": self._epoch,
                        "text": atom_data["text"][:80]
                    })
                else:
                    self._log.append({
                        "event": "rejected", "id": atom_data["id"],
                        "sim": round(sim, 4), "epoch": self._epoch,
                        "text": atom_data["text"][:80]
                    })

        # Dynamika KM
        for a in self.km.atoms:
            if not a.get("permanent"):
                a["age"] = a.get("age", 0) + 1
        self.km.step()

        # Synchronizuj T z km.atoms -> working_atoms
        km_T = {a["label"]: a["T"] for a in self.km.atoms}
        died = []
        for wa in self._working_atoms:
            if wa.id in km_T:
                wa.T = km_T[wa.id]
                wa.sim_log.append(float(np.dot(wa.vector, self.km.trace)))
            else:
                died.append(wa.id)
                self._log.append({
                    "event": "vacuum_death", "id": wa.id,
                    "text": wa.text[:60], "epoch": self._epoch
                })
        self._working_atoms = [w for w in self._working_atoms if w.id not in died]

        return {
            "epoch":    self._epoch,
            "pop":      len(self._working_atoms),
            "admitted": admitted,
            "alive":    [(w.id, round(w.T,3), round(w.sim_log[-1],4) if w.sim_log else 0)
                         for w in sorted(self._working_atoms, key=lambda x: x.T, reverse=True)],
            "queue":    len(getattr(self, "_session_queue", [])),
        }

    def get_survivors(self) -> list[dict]:
        """Atomy które przeżyły — posortowane po T."""
        result = []
        for wa in sorted(self._working_atoms, key=lambda x: x.T, reverse=True):
            result.append({
                "id":   wa.id,
                "text": wa.text,
                "T":    round(wa.T, 3),
                "sim":  round(wa.sim_log[-1], 4) if wa.sim_log else 0,
                "age":  wa.age,
            })
        return result

    def get_rejected(self) -> list[dict]:
        """Atomy które nie przeszły bramy."""
        return [e for e in self._log if e["event"] == "rejected"]

    def get_full_log(self) -> list[dict]:
        return self._log


# ===========================================================================
# LLM call (Groq)
# ===========================================================================

def call_groq(prompt: str, system: str = "", model: str = "llama-3.3-70b-versatile") -> str:
    """Wywołaj Groq API."""
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return "[GROQ_API_KEY not set — skipping LLM synthesis]"
    if not HAS_REQUESTS:
        return "[requests not available]"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json={"model": model, "messages": messages, "max_tokens": 1500},
            timeout=30,
        )
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[Groq error: {e}]"


# ===========================================================================
# Główny przepływ
# ===========================================================================

def run_agent(verbose: bool = True, use_llm: bool = True) -> dict:
    print("="*70)
    print("AGENT ROBOCZY — SYNTEZA SESJI BADAWCZEJ")
    print("Zadanie: co jest publikowalne i dlaczego")
    print("="*70)

    agent = ResearchAgent(dim=4096, seed=42)
    agent.inject_session(SESSION_ATOMS, batch_size=3)

    print(f"\nRdzeń agenta: 'publikowalność = nowość + dowód + jasność'")
    print(f"Brama: {agent.gate:.4f}")
    print(f"Atomów sesji do przetworzenia: {len(SESSION_ATOMS)}")
    print(f"Injecting {len(SESSION_ATOMS)} atoms, 3/epoch...\n")

    # Ile epok potrzeba by przetworzyć wszystkie atomy?
    n_epochs = math.ceil(len(SESSION_ATOMS) / 3) + 30  # +30 dla stabilizacji

    if verbose:
        print(f"{'ep':>4} | {'pop':>4} | {'queue':>5} | "
              f"{'admitted':>10} | alive (id: T, sim)")
        print("-"*75)

    for ep in range(n_epochs):
        result = agent.step()

        if verbose:
            admitted_str = ",".join(result["admitted"]) if result["admitted"] else "—"
            alive_top3   = " | ".join(
                f"{a[0]}:{a[1]}" for a in result["alive"][:3]
            )
            print(f"  {result['epoch']:3d} | {result['pop']:4d} | "
                  f"{result['queue']:5d} | {admitted_str:12s} | {alive_top3}")

    # Wyniki
    survivors = agent.get_survivors()
    rejected  = agent.get_rejected()

    print(f"\n{'='*70}")
    print(f"WYNIK SELEKCJI GEOMETRYCZNEJ")
    print(f"{'='*70}")
    print(f"\nPrzeżyło bramę i dynamikę: {len(survivors)}/{len(SESSION_ATOMS)} atomów")
    print(f"Odrzucono przy wejściu:    {len(rejected)} atomów\n")

    print("PRZEŻAŁE (posortowane po temperaturze):")
    for s in survivors:
        print(f"  [{s['id']}] T={s['T']:.3f} sim={s['sim']:.4f}")
        print(f"       {s['text'][:90]}")

    if rejected:
        print(f"\nODRZUCONE PRZY BRAMIE (sim < {agent.gate:.4f}):")
        for r in rejected:
            print(f"  [{r['id']}] sim={r['sim']:.4f}  {r['text'][:70]}")

    # LLM synthesis
    if use_llm and os.environ.get("GROQ_API_KEY"):
        print(f"\n{'='*70}")
        print("SYNTEZA LLM")
        print(f"{'='*70}\n")

        survivors_text = "\n".join(
            f"- [{s['id']}] (T={s['T']:.2f}): {s['text']}"
            for s in survivors
        )
        rejected_text = "\n".join(
            f"- [{r['id']}] (sim={r['sim']:.4f}): {r['text'][:80]}"
            for r in rejected
        )

        system_prompt = """Jesteś recenzentem naukowym. Oceniasz które wyniki badań zasługują na publikację.
Kryterium: nowość + dowód empiryczny + jasność.
Odpowiadaj po polsku, konkretnie, bez zbędnych pochwał."""

        user_prompt = f"""Geometryczna selekcja wyłoniła następujące wyniki z sesji badawczej nad KarmazynMatrix/HSS:

PRZEŻAŁE (wybrane przez system):
{survivors_text}

ODRZUCONE (nie przeszły bramy geometrycznej):
{rejected_text}

Na podstawie tej selekcji:
1. Które 3-5 wyników są najważniejsze dla publikacji i dlaczego?
2. Czy selekcja geometryczna wybrała właściwie? Co ewentualnie pominęła?
3. Jaki byłby tytuł i główna teza artykułu obejmującego te wyniki?

Bądź krótki i konkretny."""

        synthesis = call_groq(user_prompt, system_prompt)
        print(synthesis)
    else:
        print("\n[Ustaw GROQ_API_KEY dla syntezy LLM]")
        print("Przeżałe atomy są dostępne jako dane wejściowe do manualnej syntezy.")

    return {
        "survivors": survivors,
        "rejected":  rejected,
        "log":       agent.get_full_log(),
        "n_total":   len(SESSION_ATOMS),
    }


if __name__ == "__main__":
    result = run_agent(verbose=True, use_llm=True)

    print(f"\n{'='*70}")
    print("PODSUMOWANIE AGENTA")
    print(f"{'='*70}")
    print(f"  Atomów wejściowych:  {result['n_total']}")
    print(f"  Przeżałych:          {len(result['survivors'])}")
    print(f"  Odrzuconych:         {len(result['rejected'])}")
    print(f"  Procent selekcji:    {len(result['survivors'])/result['n_total']:.0%}")
    print()
    print("  Agent zakończył pracę.")
    print("  Trace = spójny widok tego co publikowalne z tej sesji.")
