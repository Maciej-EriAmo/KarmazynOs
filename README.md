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

## Runtime layout (canonical 2026)

```
kernel/          Python kernel (atoms, substrate, facade) — default boot Store
software/        boot, mini-Lisp guest, phi
LUA/             Lua guest (tools language)
native/          Rust substrate (reach-GC + C ABI; tests / migration)
holo/            Linux HSS LSM (C) — security bridge, optional
archiwum/        legacy monolit (old shell/studio)
```

| Path | Role |
|---|---|
| `karmazyn_boot.py` | Live REPL — default **Lua** on Store (thermal tick) |
| `karmazyn_kernel.py` | Public kernel facade (only entry for software) |
| `karmazyn_backend.py` | Substrate switch: `python` \| `native` (tests / `open_store`) |
| `LUA/` | `karmazyn_lua` guest |
| `native/karmazyn_substrate/` | Rust Store + `ksub_*` C ABI |
| `test_substrate.py` | Python law tests |
| `test_substrate_compat.py` | Python ↔ Rust golden law |
| `Documents/runtime_en.md` | Runtime guide (EN) |
| `Documents/runtime_pl.md` | Runtime guide (PL) |
| `holo/` | HSS LSM sources |
| `archiwum/` | Historical shell/studio and older modules |

**Kernel law:** temperature says *when*, reachability says *whether* (vacuum GC vs retained TOMB).

---

## Quick start

```bash
git clone https://github.com/Maciej-EriAmo/KarmazynOs
cd KarmazynOs
pip install numpy          # optional; HRR degrades without it

# Live interpreter (Lua guest on substrate)
python karmazyn_boot.py
python karmazyn_boot.py --demo
python karmazyn_boot.py --lisp --demo   # mini-Lisp guest

# Guest switch in REPL:  :guest lua | :guest exec
# Env: KARMAZYN_GUEST=lua|exec
```

```text
karmazyn> x = 10
karmazyn> return x * 2
20
```

### Tests

```bash
python -m unittest test_substrate -q
python test_substrate_compat.py -v          # needs: cargo build --release
python kernel_boundary.py kernel/ software/
```

### Native substrate (Rust)

```bash
cd native/karmazyn_substrate
cargo test && cargo build --release
cd ../..
python native/karmazyn_substrate_native.py
# KARMAZYN_SUBSTRATE=native  /  open_store(backend="native")
```

Details: [native/README.md](native/README.md) · [Documents/runtime_en.md](Documents/runtime_en.md).

Legacy `shell.py` / Studio UX (write/recall) live under **`archiwum/`**.

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
karmazyn_kernel v1.1.0     ✅  facade + reach-GC Store (Python default)
karmazyn_boot v0.5         ✅  live REPL, Lua guest, :guest switch
LUA/                       ✅  tools language on substrate
native substrate (Rust)    ✅  law + C ABI + compat tests (boot still Python)
hook registry              ✅  register_env_of / extra_reach
holo/ HSS LSM              ✅  Linux kernel bridge sources
archiwum/ shell+studio     📦  legacy
Full native boot drop-in   ⏳  phase 2–3
Crimson Loop               ⏳  introspection layer
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
