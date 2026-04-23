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

## 3. Model bezpieczeństwa

- **Ring‑LWE** do wymiany kluczy między agentami a demonem.
- **HMAC‑SHA256** fingerprint na każdym bąblu (próg Hamminga ≤ średnia + 2σ).
- **Most LSM** (`holo_lsm`) deleguje decyzje o dostępie do KarmazynOS w przestrzeni użytkownika.

## 4. Warstwa embeddingu

- **Strukturalny**: wektor losowy z ziarnem MD5.
- **Semantyczny**: analiza tokenów i bigramów z globalnym ważeniem IDF.
- Ostateczne podobieństwo: `sim = α * dot(q_struct, S_struct) + (1-α) * dot(q_sem, S_sem)`
