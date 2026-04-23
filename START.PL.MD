# KarmazynOS — Szybki Start / Quick Start

**Czas czytania: 5 minut**  
**Potrzebujesz: Python 3.10+, pip, 10 MB miejsca**

---

## 📦 Instalacja (2 minuty)

```bash
# 1. Sklonuj repozytorium
git clone https://github.com/twoja-nazwa/karmazyn-os
cd karmazyn-os

# 2. Zainstaluj zależności
pip install numpy

# 3. Uruchom powłokę
python shell.py
```

Powinieneś zobaczyć:

```
Karmazyn Shell v1.1.0 | KarmazynOS v1.1.0
Wpisz 'help' aby zobaczyć komendy, 'exit' aby wyjść.
ksh>
```

---

## 🧪 Pierwsze kroki (3 minuty)

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

### 3. Przenieś do pamięci trwałej

```
ksh> consolidate atom_a261722b
[KONSOLIDACJA] 'atom_a261722b' → bubble_4bf1eb7b01a1
```

### 4. Stwórz ideę z kilku bąbli

```
ksh> write "Czytelność kodu jest kluczowa"
Zapisano: atom_22cb7dc5

ksh> consolidate atom_22cb7dc5
[KONSOLIDACJA] 'atom_22cb7dc5' → bubble_ed64874ca798

ksh> idea "Python filozofia" atom_a261722b atom_22cb7dc5
[IDEA] Utworzono 'idea_Python_filozofia_42_a1b2c3' z 2 bąbli.
```

### 5. Wygeneruj nową myśl z idei

```
ksh> gen idea_Python_filozofia_42_a1b2c3 "jak pisać czytelny kod" 0.5
Wygenerowano atom Φ: gen_idea_Python_filozofia_42_a1b2c3_44 (temp=0.5)
```

### 6. Sprawdź statystyki

```
ksh> stats
KarmazynOS v1.1.0 | Epoka: 0
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

## 🎮 Najważniejsze komendy

| Komenda | Działanie |
|---------|-----------|
| `write "tekst"` | Zapisz nową informację |
| `recall "zapytanie"` | Znajdź w pamięci |
| `consolidate <etykieta>` | Przenieś do pamięci trwałej |
| `idea <temat> <etykiety>` | Stwórz ideę |
| `gen <idea> <prompt>` | Wygeneruj z idei |
| `spawn <idea> <prompt> --consolidate` | Wygeneruj i zapisz |
| `step 10` | Przesuń czas o 10 epok |
| `stats` | Pokaż statystyki |
| `save ./katalog` | Zapisz stan |
| `load ./katalog` | Wczytaj stan |
| `help` | Pokaż wszystkie komendy |

---

## 📂 Struktura projektu

```
karmazyn-os/
├── karmazyn.py              # Główny kernel
├── shell.py                 # Powłoka KSH
├── hss_demo.py              # Demon bezpieczeństwa
├── hss_karmazyn_matrix.py   # Macierz HSS
├── README.md                # Dokumentacja ogólna
├── HOWTO.md                 # Pełny podręcznik
├── ARCHITECTURE.md          # Opis architektury
└── examples/
    └── demo.karm            # Skrypt demonstracyjny
```

---

## 🚀 Co dalej?

- Przeczytaj [HOWTO.md](HOWTO.md) — pełny podręcznik użytkownika.
- Przeczytaj [ARCHITECTURE.md](ARCHITECTURE.md) — zrozum matematykę systemu.
- Uruchom `ksh> run examples/demo.karm` — zobacz automatyczną demonstrację.
- Eksperymentuj z `gen` i `spawn` — zobacz, jak system tworzy nowe myśli.

---

## ❓ Najczęstsze pytania

**Q: Czy dane znikają po zamknięciu?**  
A: Tak, chyba że zapiszesz stan przez `save`. Przy następnym uruchomieniu użyj `load`.

**Q: Co to jest temperatura?**  
A: Miara „świeżości” informacji w pamięci roboczej Φ. Wysoka = często używana, niska = zapominana.

**Q: Po co mi hologramy?**  
A: To generatory — na podstawie grupy bąbli tworzą nowe, podobne myśli. Nie musisz pamiętać wszystkiego — wystarczy, że masz ideę.

**Q: Czy to bezpieczne?**  
A: KarmazynOS używa kryptografii postkwantowej (Ring‑LWE). Więcej w [POSTQUANTUM.md](POSTQUANTUM.md).

---

**Gotowe. Jesteś teraz operatorem własnej pamięci termodynamicznej.** 
