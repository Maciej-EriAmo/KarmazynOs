# KarmazynOS

**Dynamiczny układ transformacji informacji z termodynamiczną semantyką danych**

*Maciej Mazur — Warsaw, 2026*

---

## Czym jest KarmazynOS

KarmazynOS nie jest systemem operacyjnym ani strukturą plików.

Jest **przestrzenią dynamicznej informacji**, gdzie struktura danych jest wynikiem geometrii relacji, a nie ich reprezentacji.

```
informacja = stabilizacja( H ∘ P ∘ A )
```

- **A** — atom: minimalny stan informacji `(S, E, T)`
- **P** — pryzmat: operator projekcji w przestrzeń interpretacji
- **H** — hologram: pole korelacji i stabilizacji atomów

Dane nie mają formatu jako bytu pierwotnego. Istnieje wyłącznie stabilizacja informacji w przestrzeni. Błędy nie istnieją — istnieje tylko **Vacuum Decay**.

---

## Trzy podstawowe byty

### Atom `A = (S, E, T)`

Minimalny stan informacji. Nie rekord. Nie plik.

| Pole | Znaczenie |
|---|---|
| `S` = `embedding` | Sygnatura strukturalna — deterministyczna, globalna, wchodzi do HRR |
| `E` | Projekcja semantyczna — lokalna, sesyjna, opcjonalna |
| `T` | Energia stabilności — `T_vac + ΔT·exp(−λ·age)` |

Atom nie przechowuje treści jako obiektu trwałego. Atom jest **stanem interpretowalności**.

### Pryzmat

Operator projekcji `P: Atom → Φ` gdzie Φ to przestrzeń interpretacji.

Trzy standardowe pryzmaty: `CORE` (rdzeń semantyczny), `IN` (kontekst wejściowy), `OUT` (interfejs zewnętrzny).

Agent z capability tylko na `OUT` dostaje szum dla `CORE` i `IN` — nie odmowę dostępu, lecz świat w którym te dane **nie istnieją**. To jest **Warp Oblivion**.

### Hologram

Interferencyjne pole korelacji atomów oparte na HRR (Holographic Reduced Representations).

```
H = {A₁, A₂, …, Aₙ} + HRR_trace
HRR_trace = A₁ ⊛ A₂ ⊛ … ⊛ Aₙ    (splot kołowy, renormalizowany)
```

Hologram nie przechowuje informacji. Hologram **wymusza dopuszczalne formy informacji**.

---

## Architektura warstw

```
┌─────────────────────────────────────────────────┐
│  HOT   active store    RAM, atom z content      │
├─────────────────────────────────────────────────┤
│  WARM  index store     RAM/plik, embedding      │
├─────────────────────────────────────────────────┤
│  COLD  archive store   dysk, Ring-LWE (N=64)    │
└─────────────────────────────────────────────────┘
```

**FSM lifecycle atomu:**
```
CREATED → HOT → WARM → COLD → TOMB → GC
```

**Vacuum Decay** — naturalny GC termodynamiczny. Atom poniżej progu `T_vacuum + ε` nie jest kasowany — przestaje istnieć jako informacja. Szyfrogram na dysku staje się szumem termodynamicznym.

---

## Model kryptograficzny

Bezpieczeństwo przez algebrę, nie przez listy uprawnień.

```
base_secret = HMAC(CSPRNG, Φ².tobytes())
root_key    = HMAC(base_secret, b"atom-root:" || atom.id)
s_agent     = KDF(s_sess, JSON(task, prisms))
```

Szyfrowanie pryzmatów: **Ring-LWE / LPR** (N=64, Q=3329, η=2).
Pełna specyfikacja: [HSS Paper v2.6.0](https://doi.org/10.5281/zenodo.19548693).

**Trzy niezależne rytmy** bez wspólnego zegara globalnego:
- Kryptograficzny: `epoch = floor(UTC/300)` — rotacja session_id
- Termodynamiczny: `T = T_vac + ΔT·exp(−λ·age)` — decay
- Semantyczny: `score = (α·S + (1-α)·E) × T(atom)` — recall

---

## Czego to NIE jest

| Nie jest | Jest |
|---|---|
| Lepszy firewall | Nowy model istnienia danych |
| SELinux z ML | Ontologiczna izolacja percepcji |
| Linux z nakładką | Inna kategoria niż Unix |
| Cache z TTL | Termodynamiczny model zaniku |
| Baza wektorowa | Asocjatywna pamięć przez HRR |

---

## Pliki w repozytorium

| Plik | Opis |
|---|---|
| `hss_demo.py` | HSSDaemon v2.9 — Ring-LWE, 20/20 testów |
| `holonp_hss_adapter.py` | Adapter Φ² → s_sess |
| `holonos_v04.py` | CognitiveState — termodynamika Φ |
| `holonos_integrated.py` | System zintegrowany — demo + CLI |
| `holo_lsm.c` | Linux Security Module v3.4 |
| `KarmazynOS_Spec_v06.md` | Specyfikacja fundamentów v0.6 |
| `holonos_animation.html` | Animacja demo (przeglądarka, offline) |

---

## Uruchomienie demo

```bash
pip install numpy --break-system-packages

# Pełne demo + CLI
python holonos_integrated.py

# Tylko scenariusz 3 agentów
python holonos_integrated.py --demo

# Tylko CLI (notatki + HSS)
python holonos_integrated.py --cli
```

**Wymagania:** Python 3.10+, numpy. Działa offline, bez GPU, na ARM64 (Samsung A54 / Termux).

### Przykładowy output

```
T_vacuum (v0.4):    2.2074 bit
epoch HSS:          5921360
evaluate() Agent A: score=11.797 > θ=3.311 → ZEZWÓL
evaluate() Agent B: score=1.841 ≤ θ=3.311 → ODMÓW
Agent A: 3× ✓ SYGNAŁ
Agent B: 3× SZUM ✗ (Warp Oblivion)
Agent C: out ✓ METADANE, core/in ✗ SZUM
Vacuum Decay: s_A skasowany → ODMOWA po vacuum
```

### Komendy CLI

```
add <tekst>        — dodaj atom do pamięci Φ
recall <zapytanie> — wyszukaj przez cosine × temperatura
list               — lista atomów z temperaturą
step [n]           — przesuń n epok (cooling + vacuum decay)
stats              — stan systemu
/demo              — uruchom scenariusz 3 agentów
/eval <tekst>      — sprawdź evaluate() Φ
/session           — pokaż stan sesji HSS
```

---

## Publikacje i DOI

| Dokument | DOI |
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
hss_demo.py v2.9           ✅  20/20 testów
holonos_integrated.py      ✅  działa na Samsung A54 / Termux
holo_lsm.c v3.4            ✅  Linux LSM z przestrzenią Φ
KarmazynOS_Spec_v06.md     ✅  6 rund audytu, spójna
Implementacja referencyjna  ⏳  atom.py + memory.py + cold_store.py
Crimson Loop               ⏳  introspekcja — ostatnia warstwa
```

---

## Autor

**Maciej Mazur** — niezależny badacz AI, Warszawa
GitHub: [@Maciej615](https://github.com/Maciej615) · [@Maciej-EriAmo](https://github.com/Maciej-EriAmo)
Medium: [@drwisz](https://medium.com/@drwisz)
Zenodo: [profil](https://zenodo.org/search?q=Maciej+Mazur)

---

*"System nie przechowuje danych — przechowuje stany interpretacji danych w czasie."*
