# KarmazynOS — Szybki Start

**Czas czytania: ~5 minut**  
**Potrzebujesz: Python 3.10+** (opcjonalnie `numpy` dla HRR)

Pełny opis runtime, szwów i native: **[runtime_pl.md](runtime_pl.md)**.

---

## Instalacja

```bash
git clone https://github.com/Maciej-EriAmo/KarmazynOs
cd KarmazynOs
pip install numpy          # opcjonalne — bez numpy jadro też wstanie
```

---

## Uruchomienie (kanoniczne — 2026)

```bash
# Żywy interpreter (domyślnie Lua na substracie)
python karmazyn_boot.py

# Skrypt demo
python karmazyn_boot.py --demo

# Mini-Lisp zamiast Lua
python karmazyn_boot.py --lisp
```

Po starcie:

```text
KarmazynOS — sekwencja startowa
  [ OK ] fasada jadra — v1.1.0 …
  [ OK ] warstwa wykonawcza — gosc=lua, korzen=tak
karmazyn>
```

### Pierwsze linie (Lua)

```text
karmazyn> x = 10
karmazyn> return x * 2
20
karmazyn> :help
karmazyn> :stats
karmazyn> :guest exec
karmazyn> (+ 1 2)
3
```

To **aktywny interpreter** na żywym Store (tick w tle, reach-GC) — nie jednorazowy skrypt.

### Program wieloplikowy (projekt → bąbel)

```bash
python karmazyn_boot.py --project LUA/examples/hello
```

```text
karmazyn> :check
check: OK
karmazyn> :run
=== hello project ===
witaj, Karmazyn
…
karmazyn> return require("util").banner()
```

Albo bez pełnego OS:

```bash
cd LUA
python run_lua.py run examples/hello
python run_lua.py check examples/hello
```

**Sandbox = bąbel:** gość nie ma dostępu do dysku; host montuje katalog projektu.

### Narzędzia OS (`lua_bin` + `karmazyn.*`)

```text
karmazyn> :tool           # lista
karmazyn> :tool ls
karmazyn> :tool whoami
karmazyn> :tool step      # pyta o liczbę ticków
karmazyn> :tool ps        # agenci (po spawn_agent)
karmazyn> :tool lsh       # hologramy / idee
karmazyn> :tool kedit     # edycja atomu
```

API hosta i jak pisać tool: [tools_lua.md](tools_lua.md).

---

## Testy (opcjonalnie)

```bash
python -m unittest test_substrate -q
python test_substrate_compat.py -v    # Python ↔ Rust (po cargo build --release)
cd LUA && python _run_tests.py        # gość Lua (~151)
cd software && python test_host_tools.py -v   # karmazyn.* + lua_bin smoke
```

---

## Archiwum / stary shell

Historyczny `shell.py` / `studio.py` (ksh, write/recall) leży w **`archiwum/`**.  
Nowy kanon to `karmazyn_boot.py` + `kernel/` + `LUA/`.

---

## Starszy przewodnik (Φ write/recall)

Poniżej zachowany skrót mentalnego modelu „write / recall / bąbel” (archiwalny UX).  
Dla aktualnego REPL użyj sekcji powyżej i [runtime_pl.md](runtime_pl.md).

### 1. Zapisz myśl (model archiwalny)

```
ksh> write "Python jest językiem wysokiego poziomu"
Zapisano: atom_a261722b
```

### 2. Przypomnij sobie

```
ksh> recall "język programowania"
1. [phi] atom_a261722b (score=0.823)
```

### 3. Przenieś do pamięci trwałej (bąbel)

```
ksh> consolidate $LAST
[KONSOLIDACJA] 'atom_a261722b' → bubble_4bf1eb7b01a1
```

### 4. Stwórz ideę z kilku bąbli

```
ksh> write "Czytelność kodu jest kluczowa"
ksh> consolidate $LAST
ksh> idea "Python filozofia" atom_a261722b atom_22cb7dc5
[IDEA] Utworzono 'idea_Python_filozofia_0_a1b2c3' z 2 bąbli.
```

### 5. Wygeneruj nową myśl z idei

```
ksh> gen idea_Python_filozofia_0_a1b2c3 "jak pisać czytelny kod" 0.5
Wygenerowano atom Φ: gen_idea_Python_filozofia_0_a1b2c3_1 (temp=0.5)
```

### 6. Sprawdź statystyki

```
ksh> stats
KarmazynOS v1.1.1 | Epoka: 0
Temperatura Φ: 4.85 | T_vacuum: 5.7187
Atomy Φ: 3 | Bąble: 2 (rozpad: 0)
Idee: 1 | Bias: 1.432
```

### 7. Zapisz stan

```
ksh> save ./moj_stan
Stan zapisany w ./moj_stan
```

---

## Albo użyj Studio webowego

```bash
python studio.py
# Otwórz http://localhost:8080 w przeglądarce
# Na Termux: termux-open-url http://localhost:8080
```

Studio daje trzy panele: atomy Φ z wizualizacją temperatury po lewej, edytor Python z live execution na środku, bąble po prawej. Możesz uruchamiać kod Python bezpośrednio w kontekście KarmazynOS (`ko`, `phi`, `bubbles`, `np` dostępne od razu).

---

## Najważniejsze komendy

| Komenda | Działanie |
|---------|-----------|
| `write "tekst"` | Zapisz nową informację do Φ |
| `recall "zapytanie"` | Znajdź w pamięci |
| `consolidate <etykieta>` | Przenieś do pamięci trwałej |
| `idea <temat> <etykiety>` | Stwórz ideę |
| `gen <idea> <prompt>` | Wygeneruj nową myśl z idei |
| `spawn <idea> <prompt> --consolidate` | Wygeneruj i zapisz trwale |
| `step 10` | Przesuń czas o 10 epok |
| `stats` | Pokaż statystyki |
| `save ./katalog` | Zapisz stan |
| `load ./katalog` | Wczytaj stan |
| `help` | Pokaż wszystkie komendy |

---

## Formaty persystencji

KarmazynOS obsługuje dwa formaty zapisu:

**Domyślny** (`save`/`load` w shellu):
```
moj_stan/
    meta.json        # epoka, klucz p2s, wersja
    hss_matrix.npz   # wektory atomów
    phi_sem.npz      # wektory semantyczne
    bubbles.pkl      # store bąbli
    holograms.json   # dane hologramów
```

**Format Soul** (zalecany, bardziej odporny):
```python
from soul_store import save_soul, load_soul
save_soul(ko, "./moj_stan")
load_soul(ko, "./moj_stan")
# Tworzy: session.soul (JSONL) + vectors.npz
```

---

## Struktura projektu

```
KarmazynOs/
├── karmazyn.py              # Główne jądro
├── hss_demo.py              # Demon bezpieczeństwa (Ring-LWE)
├── hss_karmazyn_matrix.py   # Macierz atomów
├── shell.py                 # Powłoka ksh
├── studio.py                # Studio webowe
├── soul_store.py            # Persystencja .soul
├── bubblefs.py              # Format wymiany BubbleFS
├── karmazyn_comm.py         # Menadżer komunikacji
├── karmazyn_ui/             # Design Language
│   ├── tokens.py
│   ├── states.py
│   └── renderer.py
├── static/
│   ├── karmazyn.css
│   └── karmazyn_tokens.js
├── how_to.md                # Pełny podręcznik (PL)
└── how_to_en.md             # Pełny podręcznik (EN)
```

---

## Najczęstsze pytania

**Q: Czy dane znikają po zamknięciu?**
A: Tak, chyba że zapiszesz stan przez `save`. Przy następnym uruchomieniu użyj `load`. Format `.soul` jest bardziej odporny między wersjami Pythona.

**Q: Co to jest temperatura?**
A: Miara świeżości informacji w pamięci roboczej Φ. Wysoka = niedawno używana, niska = zapominana. Atomy poniżej `T_vacuum` przechodzą Vacuum Decay i są automatycznie usuwane.

**Q: Po co mi hologramy?**
A: To struktury generatywne — na podstawie grupy bąbli tworzą nowe semantycznie powiązane myśli. `gen` i `spawn` używają ich jako punktu startowego dla generacji.

**Q: Co to jest model kryptograficzny?**
A: KarmazynOS używa postkwantowej kryptografii Ring-LWE do izolacji pryzmatów. Każdy bąbel ma klucz pochodny od historii sesji Φ² — dane są nieczytelne bez historii sesji. Szczegóły: [HSS Paper](https://doi.org/10.5281/zenodo.19548693).

---

**Gotowe. Jesteś teraz operatorem własnej pamięci termodynamicznej.**
