# KarmazynOS

**A dynamic information transformation system with thermodynamic data semantics**

*Maciej Mazur — Warsaw, 2026*

---

## What is KarmazynOS

KarmazynOS is not an operating system. It is not a file system.

It is a **space of dynamic information**, where data structure is the result of geometric relations — not their representation.

```
information = stabilization( H ∘ P ∘ A )
```

- **A** — atom: minimal unit of information state `(S, E, T)`
- **P** — prism: projection operator into interpretation space
- **H** — hologram: correlation and stabilization field of atoms

Data has no format as a primary entity. Only stabilization of information in space exists. Errors do not exist — only **Vacuum Decay**.

---

## Three fundamental entities

### Atom `A = (S, E, T)`

The minimal unit of information state. Not a record. Not a file.

| Field | Meaning |
|---|---|
| `S` = `embedding` | Structural signature — deterministic, global, enters HRR |
| `E` | Semantic projection — local, session-scoped, optional |
| `T` | Stability energy — `T_vac + ΔT·exp(−λ·age)` |

An atom does not store content as a persistent object. An atom is a **state of interpretability**.

### Prism

Projection operator `P: Atom → Φ` where Φ is the interpretation space.

Three standard prisms: `CORE` (semantic core), `IN` (input context), `OUT` (external interface).

An agent with capability only on `OUT` receives noise for `CORE` and `IN` — not an access denial, but a world in which those data **do not exist**. This is **Warp Oblivion**.

### Hologram

An interference correlation field of atoms based on HRR (Holographic Reduced Representations).

```
H = {A₁, A₂, …, Aₙ} + HRR_trace
HRR_trace = A₁ ⊛ A₂ ⊛ … ⊛ Aₙ    (circular convolution, renormalized)
```

A hologram does not store information. A hologram **enforces the admissible forms of information**.

---

## Layer architecture

```
┌─────────────────────────────────────────────────┐
│  HOT   active store    RAM, atom with content   │
├─────────────────────────────────────────────────┤
│  WARM  index store     RAM/file, embedding only │
├─────────────────────────────────────────────────┤
│  COLD  archive store   disk, Ring-LWE (N=64)    │
└─────────────────────────────────────────────────┘
```

**Atom FSM lifecycle:**
```
CREATED → HOT → WARM → COLD → TOMB → GC
```

**Vacuum Decay** — natural thermodynamic GC. An atom below threshold `T_vacuum + ε` is not deleted — it ceases to exist as information. The ciphertext on disk becomes thermodynamic noise.

---

## Cryptographic model

Security through algebra, not through access control lists.

```
base_secret = HMAC(CSPRNG, Φ².tobytes())
root_key    = HMAC(base_secret, b"atom-root:" || atom.id)
s_agent     = KDF(s_sess, JSON(task, prisms))
```

Prism encryption: **Ring-LWE / LPR** (N=64, Q=3329, η=2).
Full specification: [HSS Paper v2.6.0](https://doi.org/10.5281/zenodo.19548693).

**Three independent rhythms** with no shared global clock:
- Cryptographic: `epoch = floor(UTC/300)` — session_id rotation
- Thermodynamic: `T = T_vac + ΔT·exp(−λ·age)` — decay
- Semantic: `score = (α·S + (1-α)·E) × T(atom)` — recall

---

## What this is NOT

| Not | Is |
|---|---|
| A better firewall | A new model of data existence |
| SELinux with ML | Ontological isolation of perception |
| Linux with an overlay | A different category than Unix |
| Cache with TTL | Thermodynamic decay model |
| A vector database | Associative memory through HRR |

---

## Repository files

| File | Description |
|---|---|
| `hss_demo.py` | HSSDaemon v2.9 — Ring-LWE, 20/20 tests |
| `holonp_hss_adapter.py` | Adapter Φ² → s_sess |
| `holonos_v04.py` | CognitiveState — thermodynamics of Φ |
| `holonos_integrated.py` | Integrated system — demo + CLI |
| `holo_lsm.c` | Linux Security Module v3.4 |
| `KarmazynOS_Spec_v06.md` | Core specification v0.6 |
| `holonos_animation.html` | Demo animation (browser, offline) |

---

## Running the demo

```bash
pip install numpy --break-system-packages

# Full demo + CLI
python holonos_integrated.py

# Three-agent scenario only
python holonos_integrated.py --demo

# CLI only (notes + HSS)
python holonos_integrated.py --cli
```

**Requirements:** Python 3.10+, numpy. Runs offline, no GPU, on ARM64 (Samsung A54 / Termux).

### Sample output

```
T_vacuum (v0.4):    2.2074 bit
epoch HSS:          5921360
evaluate() Agent A: score=11.797 > θ=3.311 → ALLOW
evaluate() Agent B: score=1.841 ≤ θ=3.311 → DENY
Agent A: 3× ✓ SIGNAL
Agent B: 3× NOISE ✗ (Warp Oblivion)
Agent C: out ✓ METADATA, core/in ✗ NOISE
Vacuum Decay: s_A revoked → DENY after vacuum
```

### CLI commands

```
add <text>         — add atom to Φ memory
recall <query>     — search via cosine × temperature
list               — list atoms with temperature
step [n]           — advance n epochs (cooling + vacuum decay)
stats              — system state
/demo              — run three-agent scenario
/eval <text>       — query evaluate() of Φ
/session           — show HSS session state
```

---

## Publications and DOI

| Document | DOI |
|---|---|
| Holon Architecture | [10.5281/zenodo.19371554](https://doi.org/10.5281/zenodo.19371554) |
| HolonFS | [10.5281/zenodo.19366419](https://doi.org/10.5281/zenodo.19366419) |
| Prismatic Attention | [10.5281/zenodo.19371560](https://doi.org/10.5281/zenodo.19371560) |
| Harmonic Attention | [10.5281/zenodo.19387523](https://doi.org/10.5281/zenodo.19387523) |
| HSS — Holographic Session Spaces | [10.5281/zenodo.19548693](https://doi.org/10.5281/zenodo.19548693) |
| HSL — Holographic Security Layer | [10.5281/zenodo.19608591](https://doi.org/10.5281/zenodo.19608591) |

---

## Status

```
hss_demo.py v2.9           ✅  20/20 tests passing
holonos_integrated.py      ✅  running on Samsung A54 / Termux
holo_lsm.c v3.4            ✅  Linux LSM with Φ-space
KarmazynOS_Spec_v06.md     ✅  6 audit rounds, consistent
Reference implementation    ⏳  atom.py + memory.py + cold_store.py
Crimson Loop               ⏳  introspection — final layer
```

---

## Author

**Maciej Mazur** — independent AI researcher, Warsaw
GitHub: [@Maciej615](https://github.com/Maciej615) · [@Maciej-EriAmo](https://github.com/Maciej-EriAmo)
Medium: [@drwisz](https://medium.com/@drwisz)
Zenodo: [profile](https://zenodo.org/search?q=Maciej+Mazur)

---

*"The system does not store data — it stores states of data interpretation over time."*
