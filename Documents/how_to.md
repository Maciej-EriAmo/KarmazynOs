# 📘 KarmazynOS — Przewodnik użytkownika

**Wersja 1.0.0** (warstwa Φ write/recall — model klasyczny)  
**Runtime 2026 (boot + Lua):** → **[runtime_pl.md](runtime_pl.md)** · **[START.PL.MD](START.PL.MD)**

```bash
# Kanon 2026 — żywy interpreter
python karmazyn_boot.py
python karmazyn_boot.py --demo
```

Poniżej: klasyczny przewodnik ksh (`write` / `recall`) — historycznie w `archiwum/` / starszych skryptach.

---

KarmazynOS to termodynamiczne jądro pamięci — system, który zapamiętuje, przypomina, zapomina i tworzy nowe idee. Pracuje w trzech warstwach:

| Warstwa       | Stan fizyczny | Opis |
|---------------|---------------|------|
| **Φ (Phi)**   | plazma        | Pamięć robocza — informacje konkurują o uwagę, stygną z czasem. |
| **Bąbel**     | ciało stałe   | Pamięć trwała — dane przechowywane wiernie, ale z czasem mogą „cichnąć”. |
| **Hologram**  | pole          | Idea — nie przechowuje konkretów, tylko generuje nowe warianty. |

Klasyczny UX: **Karmazyn Shell (ksh)** (archiwum). Runtime 2026: **`karmazyn_boot`** + Lua.

---

## 🚀 Pierwsze kroki (klasyczny ksh)

Uruchom powłokę (jeśli dostępna w Twojej instalacji / archiwum):

```bash
python shell.py
```

Po uruchomieniu zobaczysz:

```
Karmazyn Shell v1.0 | KarmazynOS v1.0.0
Wpisz 'help' aby zobaczyć dostępne komendy, 'exit' aby wyjść.
ksh>
```

Aby wyświetlić listę wszystkich komend:

```bash
ksh> help
```

---

## ✍️ Podstawowe operacje na pamięci

### Dodawanie informacji do Φ

```bash
ksh> write "Python pozwala szybko prototypować"
Zapisano: atom_abc123
```

Każdy zapis otrzymuje unikalną etykietę. Ostatnia etykieta jest dostępna w zmiennej `$LAST`.

### Przypominanie (recall)

```bash
ksh> recall "język programowania"
1. [phi] atom_abc123 (score=0.823)
```

System przeszukuje zarówno pamięć roboczą Φ, jak i bąble. Wyniki są sortowane według dopasowania semantycznego.

### Konsolidacja — przeniesienie do pamięci trwałej

```bash
ksh> consolidate $LAST
[KONSOLIDACJA] 'atom_abc123' → bubble_xyz789
```

Od tej chwili informacja jest bąblem i nie zniknie po ostygnięciu Φ (choć może podlegać powolnemu rozkładowi).

---

## 🧠 Zarządzanie bąblami

| Komenda | Składnia | Opis |
|---------|----------|------|
| **decay** | `decay <etykieta> <rate>` | Przyspiesza rozpad bąbla (np. 0.05 = 5% na epokę) |
| **refresh** | `refresh <etykieta>` | Resetuje proces rozpadu — bąbel wraca do pełnej żywotności |
| **revoke** | `revoke <etykieta>` | Unieważnia bąbel (Warp Oblivion) — staje się nieczytelny |
| **reactivate** | `reactivate <etykieta>` | Przywraca bąbel do pamięci roboczej Φ jako nowy atom |

**Przykłady:**

```bash
ksh> decay atom_abc123 0.05
ksh> refresh atom_abc123
ksh> revoke atom_abc123
ksh> reactivate atom_abc123
```

---

## 💡 Praca z ideami (hologramami)

### Tworzenie idei

```bash
ksh> idea "Python filozofia" b1 b2 b3
[IDEA] Utworzono 'idea_Python_filozofia_42_a1b2c3' z 3 bąbli.
```

### Generowanie nowych atomów z idei

```bash
ksh> gen idea_Python_filozofia_42_a1b2c3 "czytelność kodu" 0.5
```

- **prompt** — kierunek generacji
- **temperatura** — im wyższa, tym więcej kreatywności (domyślnie 0.3)

### Spawn (generowanie + opcjonalna konsolidacja)

```bash
ksh> spawn idea_Python_filozofia_42_a1b2c3 "wydajność" --consolidate
```

### Rehydratacja idei

```bash
ksh> rehydrate idea_Python_filozofia_42_a1b2c3
```

---

## ⏳ Upływ czasu

System mierzy czas w **epokach**. Co epokę atomy Φ stygną, a bąble z decay tracą żywotność.

```bash
ksh> step 10          # przesuń czas o 10 epok
ksh> step             # jeden krok
```

---

## 📊 Monitorowanie systemu

```bash
ksh> stats
```

Przykład wyjścia:

```
KarmazynOS v1.0.0
Epoka: 52 | Temperatura Φ: 3.21 | T_vacuum: 5.7187
Atomy Φ: 12 | Bąble: 7 (w tym rozpadających się: 2)
Bąble unieważnione: 1 | Idee (hologramy): 2
Bias bąbli: 1.854
```

---

## 🧪 Skrypty .karm

Możesz zapisywać sekwencje komend w plikach z rozszerzeniem `.karm`.

**Przykład `demo.karm`:**

```karm
write "KarmazynOS jest systemem termodynamicznym"
consolidate $LAST
write "Używa trzech warstw pamięci"
idea "podstawy" $LAST
step 5
spawn idea_podstawy "architektura" --consolidate
stats
```

Uruchomienie:

```bash
ksh> run demo.karm
```

---

## 🔐 Agenci (funkcja zaawansowana)

```bash
ksh> agent derive alicja "analiza danych" core in
ksh> agent read 101 atom_abc123 --bubble
```

---

## 📌 Podsumowanie wszystkich komend

| Komenda              | Opis |
|----------------------|------|
| `write <tekst>`      | Dodaje atom do Φ |
| `recall <zapytanie>` | Szuka w Φ i bąblach |
| `consolidate <etykieta>` | Przenosi atom do bąbla |
| `reactivate <etykieta>` | Przywraca bąbel do Φ |
| `revoke <etykieta>`  | Unieważnia bąbel |
| `decay <etykieta> <rate>` | Ustawia tempo rozpadu |
| `refresh <etykieta>` | Resetuje rozpad bąbla |
| `idea <temat> <lista etykiet>` | Tworzy hologram (ideę) |
| `ideas`              | Lista wszystkich idei |
| `gen <id_idei> <prompt> [temp]` | Generuje atom Φ z idei |
| `spawn <id_idei> <prompt> [--consolidate]` | Generuje i opcjonalnie konsoliduje |
| `rehydrate <id_idei>` | Odtwarza atomy z idei |
| `stats`              | Statystyki systemu |
| `step [n]`           | Przesuwa czas o n epok |
| `gc`                 | Ręczne czyszczenie revoked bąbli |
| `run <plik.karm>`    | Wykonuje skrypt |
| `help [komenda]`     | Pomoc |
| `exit`               | Wyjście z powłoki |

---

## 🧭 Filozofia KarmazynOS

- Pamięć to nie magazyn — informacje mają **temperaturę**, **żywotność** i mogą ewoluować.
- Idee nie są faktami — hologramy generują warianty, nie odtwarzają przeszłości.
- Czas płynie — wszystko podlega termodynamice.

**Z KarmazynOS nie tylko przechowujesz dane — hodujesz myśli.**
```
