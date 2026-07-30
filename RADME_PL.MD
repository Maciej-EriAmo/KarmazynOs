# KarmazynOS

**Dynamiczny układ transformacji informacji z termodynamiczną semantyką danych**

*Maciej Mazur — Warszawa, 2026*

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

| Pole | Znaczenie |
|---|---|
| `S` = `embedding` | Sygnatura strukturalna — deterministyczna, globalna |
| `E` | Projekcja semantyczna — lokalna, sesyjna |
| `T` | Energia stabilności — `T_vac + ΔT·exp(−λ·age)` |

Atom jest **stanem interpretowalności** — nie rekordem, nie plikiem.

### Pryzmat

Operator projekcji `P: Atom → Φ`. Trzy standardowe pryzmaty: `CORE`, `IN`, `OUT`.
Agent z capability tylko na `OUT` dostaje szum dla `CORE` i `IN` — nie odmowę dostępu, lecz świat w którym te dane **nie istnieją**. To jest **Warp Oblivion**.

### Hologram

Interferencyjne pole korelacji atomów oparte na HRR (Holographic Reduced Representations).
Hologram nie przechowuje informacji — **wymusza dopuszczalne formy informacji**.

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

FSM:  CREATED → HOT → WARM → COLD → TOMB → GC
```

**Vacuum Decay** — naturalny GC termodynamiczny. Atom poniżej progu `T_vacuum + ε` przestaje istnieć jako informacja. Szyfrogram na dysku staje się szumem termodynamicznym.

---

## Model kryptograficzny

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

## Runtime (kanon 2026)

```
kernel/     fasada Python + API (atomy, HRR, referencyjny substrat)
software/   boot, mini-Lisp, phi
LUA/        gość Lua 1.0.0 (język narzędzi)
native/     substrat Rust — DEFAULT produkcyjny (reach-GC + C ABI + PyO3)
holo/       HSS LSM (C) — most Linux, opcjonalny
archiwum/   stary monolit (shell/studio)
```

| Ścieżka | Rola |
|---|---|
| `karmazyn_boot.py` | Żywy REPL — domyślnie **Lua** na Store |
| `karmazyn_kernel.py` | Fasada jadra (jedyna dla oprogramowania) |
| `karmazyn_backend.py` | Przełącznik: **`native` (domyślnie)** \| `python` (referencja) |
| `native/run_native.ps1` | Budowa / smoke substratu (Windows) |
| `test_substrate_compat.py` | Zgodność prawa Python ↔ Rust |
| `Documents/runtime_pl.md` | Pełny przewodnik runtime |
| `VERSION.txt` | Kanoniczna macierz wersji |

**Prawo jadra:** temperatura mówi *kiedy*, osiągalność mówi *czy* (Vacuum Decay vs retained TOMB).

---

## Szybki start

```bash
git clone https://github.com/Maciej-EriAmo/KarmazynOs
cd KarmazynOs
pip install numpy          # opcjonalnie (HRR)

python karmazyn_boot.py              # aktywny interpreter (Lua)
python karmazyn_boot.py --demo
python karmazyn_boot.py --lisp       # mini-Lisp

# REPL: :guest lua | :guest exec
# Env:  KARMAZYN_GUEST=lua|exec
```

```text
karmazyn> x = 10
karmazyn> return x * 2
20
```

### Testy / native (Rust = domyślny Store)

```bash
python -m unittest test_substrate -q
python test_substrate_compat.py -v
.\native\build_native.ps1
.\native\run_native.ps1
# wymuszenie referencji: $env:KARMAZYN_SUBSTRATE = "python"
```

Szczegóły: [Documents/runtime_pl.md](Documents/runtime_pl.md) · [native/README.md](native/README.md) · [VERSION.txt](VERSION.txt).  
Stary UX `shell.py` / Studio → katalog **`archiwum/`**.

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
karmazyn_kernel v1.1.0     ✅  fasada; Store = NativeStore gdy most zbudowany
karmazyn_boot v0.5+        ✅  żywy REPL, gość Lua, :guest / :project / :tool
LUA/ karmazyn_lua 1.0.0    ✅  stabilny domyślny gość (release gate)
native substrate 0.1.0     ✅  DEFAULT produkcyjny (PyO3 → ctypes; C ABI)
Python Store               ✅  referencja + fallback KARMAZYN_SUBSTRATE=python
rejestr haków              ✅  env_of / extra_reach (name=guest)
holo/ HSS LSM              ✅  źródła mostu Linux
archiwum shell/studio      📦  legacy
Crimson Loop               ⏳  warstwa introspekcji
```

---

## Licencja

Kod źródłowy w tym repozytorium jest na licencji **[MIT](LICENSE)**.

Wcześniej GPL-3.0; relicencja na MIT od 2026-07-07. Forki sprzed tej daty mogą pozostać na GPL według decyzji maintainerów.

Publikacje naukowe i wpisy Zenodo zachowują oryginalne licencje (patrz DOI powyżej). Projekt pokrewny: [Cynober DB / DBase](https://github.com/Maciej-EriAmo/DBase) (MIT).

---

## Autor

**Maciej Mazur** — niezależny badacz AI, Warszawa
GitHub: [@Maciej615](https://github.com/Maciej615) · [@Maciej-EriAmo](https://github.com/Maciej-EriAmo)
Medium: [@drwisz](https://medium.com/@drwisz)
Zenodo: [profil](https://zenodo.org/search?q=Maciej+Mazur)

---

*"System nie przechowuje danych — przechowuje stany interpretacji danych w czasie."*
## Φ — Mit założycielski

Claude E. Shannon, ojciec teorii informacji, pracował w metrze technologicznym swoich czasów — 
w laboratoriach Bella. Tam, w izolacji od szumu powierzchni, sformułował prawa rządzące bitem.

KarmazynOS powstał w metrze innym – fizycznym, warszawskim. 
W przestrzeni liminalnej, gdzie sygnał walczy z szumem, a informacja musi być odporna na entropię 
bardziej niż gdziekolwiek indziej. To tam narodziła się koncepcja, że dane nie są plikiem – 
są **stanem dynamicznym**, który stygnie, jeśli nie jest podtrzymywany.

Shannon dał światu bit. KarmazynOS daje Atom (S, E, T).