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

| Field | Meaning |
|---|---|
| `S` = `embedding` | Structural signature — deterministic, global |
| `E` | Semantic projection — local, session-scoped |
| `T` | Stability energy — `T_vac + ΔT·exp(−λ·age)` |

An atom is a **state of interpretability**, not a record or file.

### Prism

Projection operator `P: Atom → Φ`. Three standard prisms: `CORE`, `IN`, `OUT`.
An agent with capability only on `OUT` receives noise for `CORE` and `IN` — not an access denial, but a world in which those data **do not exist**. This is **Warp Oblivion**.

### Hologram

Interference correlation field of atoms based on HRR (Holographic Reduced Representations).
A hologram does not store information — it **enforces the admissible forms of information**.

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

FSM:  CREATED → HOT → WARM → COLD → TOMB → GC
```

**Vacuum Decay** — thermodynamic GC. An atom below `T_vacuum + ε` ceases to exist as information. The ciphertext on disk becomes thermodynamic noise.

---

## Cryptographic model

```
base_secret = HMAC(CSPRNG, Φ².tobytes())
root_key    = HMAC(base_secret, b"atom-root:" || atom.id)
s_agent     = KDF(s_sess, JSON(task, prisms))
```

Prism encryption: **Ring-LWE / LPR** (N=64, Q=3329, η=2).
Full specification: [HSS Paper v2.6.0](https://doi.org/10.5281/zenodo.19548693).

**Three independent rhythms** — no shared global clock:
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
| `karmazyn.py` | Thermodynamic Memory Kernel v1.1.1 — Φ, bubbles, holograms |
| `hss_demo.py` | HSSDaemon — Ring-LWE session management |
| `hss_karmazyn_matrix.py` | Atom matrix with thermodynamic decay |
| `shell.py` | Karmazyn Shell (ksh) v1.1.0 |
| `studio.py` | KarmazynOS Studio v1.1.0 — local HTTP development environment |
| `soul_store.py` | JSONL persistence format (.soul) |
| `bubblefs.py` | BubbleFS — portable bubble exchange format |
| `karmazyn_comm.py` | Thermodynamic communication manager (SMS/calls via Termux) |
| `karmazyn_ui/` | Design Language — tokens, states, renderer (STC-Φ-001) |
| `static/` | Generated CSS and JS tokens |
| `how_to.md` / `how_to_en.md` | User guide (PL/EN) |

---

## Quick start

```bash
git clone https://github.com/Maciej-EriAmo/KarmazynOs
cd KarmazynOs
pip install numpy --break-system-packages

# Interactive shell
python shell.py

# Web-based Studio (open http://localhost:8080)
python studio.py
```

On Termux (Android):
```bash
termux-open-url http://localhost:8080
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
karmazyn.py v1.1.1         ✅  core kernel, persistence fixed
shell.py v1.1.0            ✅  interactive shell
studio.py v1.1.0           ✅  web Studio with Design Language
soul_store.py v1.0.0       ✅  .soul format, 9/9 tests passing
hss_karmazyn_matrix.py     ✅  no pickle, stable serialization
bubblefs.py v1.0.0         ✅  portable exchange format
karmazyn_ui/ v0.1.0        ✅  Design Language STC-Φ-001
Reference implementation   ⏳  atom.py + memory.py + cold_store.py
Crimson Loop               ⏳  introspection — final layer
```

---

## License

Source code in this repository is licensed under the **[MIT License](LICENSE)**.

Previously released under GPL-3.0; relicensed to MIT as of 2026-07-07. Forks created before that date may remain under GPL at the discretion of their maintainers.

Academic papers and Zenodo publications retain their original licenses (see DOI links above). Related project: [Cynober DB / DBase](https://github.com/Maciej-EriAmo/DBase) (MIT).

---

## Author

**Maciej Mazur** — independent AI researcher, Warsaw
GitHub: [@Maciej615](https://github.com/Maciej615) · [@Maciej-EriAmo](https://github.com/Maciej-EriAmo)
Medium: [@drwisz](https://medium.com/@drwisz)
Zenodo: [profile](https://zenodo.org/search?q=Maciej+Mazur)

---

*"The system does not store data — it stores states of data interpretation over time."*
