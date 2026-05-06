# KarmazynOS — Szybki Start

**Czas czytania: 5 minut**
**Potrzebujesz: Python 3.10+, numpy, 10 MB miejsca**

---

## Instalacja (2 minuty)

```bash
# 1. Sklonuj repozytorium
git clone https://github.com/Maciej-EriAmo/KarmazynOs
cd KarmazynOs

# 2. Zainstaluj zależności
pip install numpy --break-system-packages

# 3. Uruchom powłokę
python shell.py
```

Powinieneś zobaczyć:

```
Karmazyn Shell v1.1.0 | KarmazynOS v1.1.1
Wpisz 'help' aby zobaczyć komendy, 'exit' aby wyjść.
ksh>
```

---

## Pierwsze kroki (3 minuty)

### 1. Zapisz myśl

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
