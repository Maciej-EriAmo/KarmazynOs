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

## Pliki w repozytorium

| Plik | Opis |
|---|---|
| `karmazyn.py` | Termodynamiczne jądro pamięci v1.1.1 — Φ, bąble, hologramy |
| `hss_demo.py` | HSSDaemon — zarządzanie sesjami Ring-LWE |
| `hss_karmazyn_matrix.py` | Macierz atomów z termodynamicznym rozpadem |
| `shell.py` | Karmazyn Shell (ksh) v1.1.0 |
| `studio.py` | KarmazynOS Studio v1.1.0 — lokalne środowisko HTTP |
| `soul_store.py` | Format persystencji JSONL (.soul) |
| `bubblefs.py` | BubbleFS — przenośny format wymiany bąbli |
| `karmazyn_comm.py` | Termodynamiczny menadżer komunikacji (SMS/połączenia, Termux) |
| `karmazyn_ui/` | Design Language — tokeny, stany, renderer (STC-Φ-001) |
| `static/` | Wygenerowany CSS i tokeny JS |
| `how_to.md` / `how_to_en.md` | Podręcznik użytkownika (PL/EN) |

---

## Szybki start

```bash
git clone https://github.com/Maciej-EriAmo/KarmazynOs
cd KarmazynOs
pip install numpy --break-system-packages

# Interaktywna powłoka
python shell.py

# Studio webowe (otwórz http://localhost:8080)
python studio.py
```

Na Termux (Android):
```bash
termux-open-url http://localhost:8080
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
karmazyn.py v1.1.1         ✅  jądro, persystencja kluczy naprawiona
shell.py v1.1.0            ✅  interaktywna powłoka
studio.py v1.1.0           ✅  Studio webowe z Design Language
soul_store.py v1.0.0       ✅  format .soul, 9/9 testów
hss_karmazyn_matrix.py     ✅  bez pickle, stabilna serializacja
bubblefs.py v1.0.0         ✅  przenośny format wymiany
karmazyn_ui/ v0.1.0        ✅  Design Language STC-Φ-001
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
## Φ — Mit założycielski

Claude E. Shannon, ojciec teorii informacji, pracował w metrze technologicznym swoich czasów — 
w laboratoriach Bella. Tam, w izolacji od szumu powierzchni, sformułował prawa rządzące bitem.

KarmazynOS powstał w metrze innym – fizycznym, warszawskim. 
W przestrzeni liminalnej, gdzie sygnał walczy z szumem, a informacja musi być odporna na entropię 
bardziej niż gdziekolwiek indziej. To tam narodziła się koncepcja, że dane nie są plikiem – 
są **stanem dynamicznym**, który stygnie, jeśli nie jest podtrzymywany.

Shannon dał światu bit. KarmazynOS daje Atom (S, E, T).