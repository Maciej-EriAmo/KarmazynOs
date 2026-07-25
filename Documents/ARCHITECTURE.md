# Architecture of KarmazynOS

## 1. Three‑layer memory model

### Φ (Phi) — Working Memory
- Atoms compete for attention via **temperature** `T`.
- Temperature decays exponentially: `T(t+1) = T(t) * (1 - λ)`.
- Upon recall, the temperature is slightly increased: `T = T + 0.3*(T_base - T)`.
- Atoms with `T < 0.01` are removed (evaporation).

### Bubbles — Long‑term Memory
- An atom may be **consolidated** into a bubble, which stores the exact content.
- Bubble strength is governed by **liveliness**:
  `L(t) = exp(-rate * (t - t_last_recall))`
- At each recall, `t_last_recall` is shifted forward by 30% (partial regeneration).
- A **dynamic bias** `bias = 1 + 0.5*log(1 + n_eff)` gives bubbles an advantage over Φ.
- Bubbles can be **revoked** (Warp Oblivion) — the decryption key is zeroed, rendering the content unusable.

### Holograms — Generative Idea Space
- A hologram is built from several bubbles via **PCA**:
  - `proto = mean(vectors)`
  - `generators = top eigenvectors of covariance`
  - `weights = corresponding eigenvalues`
- To generate a new vector:
  `synthetic = proto * dot(q, proto) + Σ (generator_i * dot(q, gen_i) * weight_i * T) + noise`
- The synthetic vector is multiplied by the hologram’s own liveliness.

## 2. Information flow

Phi → consolidate → Bubble → archive → Hologram → generate → Phi

## 3. Security model

- **Ring‑LWE** for key exchange between agents and daemon.
- **HMAC‑SHA256** fingerprint on every bubble (Hamming threshold ≤ mean + 2σ).
- **LSM bridge** (`holo_lsm`) delegates access decisions to userspace KarmazynOS.

## 4. Embedding layer

- **Structural**: MD5‑seeded random vector.
- **Semantic**: token + bigram analysis with global IDF weighting.
- Final similarity: `sim = α * dot(q_struct, S_struct) + (1-α) * dot(q_sem, S_sem)`

---

## 5. Monorepo runtime (2026)

See **[runtime_en.md](runtime_en.md)** for the full guide.

| Layer | Implementation | Notes |
|-------|----------------|--------|
| Facade | `karmazyn_kernel` | sole software entry |
| Substrate | Python `Store` or Rust `native/` | same T×reach law |
| Guest | Lua / mini-Lisp | `eval_line`; no GC internals |
| Boot | `karmazyn_boot` | mount + REPL + thermal scheduler |
| Linux HSS | `holo/*.c` LSM | upcall transport only |

**Law:** temperature = *when*, reachability = *whether* (vacuum vs retained TOMB).  
Hooks: `register_env_of`, `register_extra_reach`, roots.  
Guest switch: `KARMAZYN_GUEST` / `:guest`. Substrate switch (tests): `KARMAZYN_SUBSTRATE` / `open_store`.
