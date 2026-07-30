# Architektura KarmazynOS

## 1. Trzywarstwowy model pamięci

### Φ (Phi) — Pamięć robocza
- Atomy konkurują o uwagę przez **temperaturę** `T`.
- Temperatura maleje wykładniczo: `T(t+1) = T(t) * (1 - λ)`.
- Przy przypomnieniu temperatura jest lekko podnoszona: `T = T + 0.3*(T_baza - T)`.
- Atomy z `T < 0.01` są usuwane (parowanie).

### Bąble — Pamięć trwała
- Atom może być **skonsolidowany** w bąbel, który przechowuje dokładną treść.
- Siła bąbla zależy od **żywotności**:
  `L(t) = exp(-rate * (t - t_ostatniego_przypomnienia))`
- Przy każdym przypomnieniu `t_ostatniego_przypomnienia` jest przesuwane do przodu o 30% (częściowa regeneracja).
- **Dynamiczny bias** `bias = 1 + 0.5*log(1 + n_eff)` daje bąblom przewagę nad Φ.
- Bąble mogą być **unieważniane** (Warp Oblivion) — klucz deszyfrujący jest zerowany, a treść staje się bezużyteczna.

### Hologramy — Generatywna przestrzeń idei
- Hologram budowany jest z kilku bąbli za pomocą **PCA**:
  - `proto = średnia(wektorów)`
  - `generatory = górne wektory własne kowariancji`
  - `wagi = odpowiadające im wartości własne`
- Generowanie nowego wektora:
  `syntetyczny = proto * dot(q, proto) + Σ (generator_i * dot(q, gen_i) * waga_i * T) + szum`
- Wektor syntetyczny jest mnożony przez żywotność hologramu.

## 2. Przepływ informacji

Phi → konsolidacja → Bąbel → archiwizacja → Hologram → generacja → Phi

## 3. Model bezpieczeństwa (HSS v2.5.0)

- **Ring‑LWE** do wymiany kluczy między agentami a demonem.
- **HMAC‑SHA256** fingerprint na każdym bąblu (próg Hamminga ≤ średnia + 2σ).
- **Most LSM** (`holo_lsm`) pełni wyłącznie rolę **upcall filter** i deleguje decyzje o dostępie do uprzywilejowanego demona `hss-daemon` w przestrzeni użytkownika (zasada "No-Plaintext-In-Kernel").
- Zamiast przestarzałego Additive Key Modification, używany jest mechanizm **KDF-Based Attenuation** wyprowadzający klucze agentów: $s_A = \text{KDF}(s_{\text{sess}}, \text{agent\_id}, \mathcal{P}_{\text{task}})$.
- **Izolacja HSS vs VM:** VM izoluje zasoby (CPU/RAM), podczas gdy HSS izoluje informacje geometrycznie. Bezpieczeństwo jest tu traktowane jako własność topologiczna przestrzeni wykonawczej, chronionej kryptograficznie, z rygorystycznym zakazem zapisu w rdzeniu Φ (AAD Context Binding).

## 4. Warstwa embeddingu

- **Strukturalny**: wektor losowy z ziarnem MD5.
- **Semantyczny**: analiza tokenów i bigramów z globalnym ważeniem IDF.
- Ostateczne podobieństwo: `sim = α * dot(q_struct, S_struct) + (1-α) * dot(q_sem, S_sem)`

---

## 5. Runtime monorepo (2026) — jadro, szwy, goście

Osobny przewodnik: **[runtime_pl.md](runtime_pl.md)**.

### 5.1 Warstwy

| Warstwa | Implementacja | Uwagi |
|---------|---------------|--------|
| Fasada | `karmazyn_kernel` | jedyne API dla oprogramowania |
| Substrat | Python `Store` **lub** Rust `native/` | to samo prawo T×reach |
| Gość | Lua (`LUA/`) / mini-Lisp (`karmazyn_exec`) | `eval_line`; nie zna wnętrza GC |
| Boot | `karmazyn_boot` | montaż + REPL + scheduler |
| HSS w Linux | `holo/*.c` LSM | czysty transport upcall; semantyka poza jądrem OS |

### 5.2 Prawo reach-GC (kanon substratu)

```
temperatura  →  KIEDY atom może stać się kandydatem do GC
osiągalność  →  CZY wolno go usunąć
  zimny + nieosiągalny  →  vacuum (reap)
  zimny + osiągalny     →  retained TOMB
```

Osiągalność: korzenie (`set_root`) + łańcuch `parent` bąbli + haki  
`register_env_of` (domknięcia/tabele) + `register_extra_reach` (ramki).

### 5.3 Przełączniki

- **Gość:** `KARMAZYN_GUEST`, `--lua`/`--lisp`, REPL `:guest`
- **Substrat:** `KARMAZYN_SUBSTRATE`, `open_store(backend=…)`  
  **Domyślnie:** Rust `NativeStore` (gdy most zbudowany); Python Store = referencja / fallback.

### 5.4 Granica jadro ↛ oprogramowanie

`kernel_boundary.py` — jadro nie importuje software (twardy fail w CI/build).
