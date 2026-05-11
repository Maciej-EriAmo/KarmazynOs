# Lua dla KarmazynOS — kurs interaktywny

> *Schola Mechanica — sekcja Lingua Sacra*  
> Materiał szkoleniowy dla operatorów Φ-space  
> Wersja 1.0

---

## O kursie

Ten kurs uczy języka **Lua 5.4** od podstaw aż do zaawansowanego embeddingu w hostach C, sandboxingu i pisania DSL-i konfiguracyjnych. Cel końcowy: po przejściu wszystkich modułów potrafisz napisać politykę HSS w Lua, osadzić interpreter w komponencie KarmazynOS i bezpiecznie uruchamiać niezaufane skrypty użytkowników.

Kurs jest podzielony na **12 modułów** (plus opcjonalny Moduł 0 dla osób bez doświadczenia w programowaniu). Każdy moduł to 4-6 lekcji + sprawdzian końcowy. Każda lekcja zawiera:

1. **Cel** — co umiesz po lekcji
2. **Materiał** — pojęcia i przykłady
3. **Pułapki** — rzeczy, które *boli* gdy się przeoczy
4. **Zadania** — 3-5 problemów do rozwiązania samodzielnie
5. **Rozwiązania** — pełen kod z wyjaśnieniem (dopiero po próbie!)
6. **Sprawdź się** — lista pytań kontrolnych

**Ważne:** Zadania rozwiązuj **zanim** spojrzysz na rozwiązanie. Czytanie rozwiązań bez próby = czytanie podręcznika. Próbowanie + porównywanie z rozwiązaniem = nauka.

---

## Dla kogo

- Programiści znający dowolny inny język (Python, C, JavaScript, Ruby...)
- Architekci systemów planujący wprowadzenie języka skryptowego do swojego produktu
- Operatorzy KarmazynOS / HSS, którzy będą pisać polityki Φ-space

**NIE** jest to kurs dla całkowicie początkujących w programowaniu. Zakładamy, że wiesz co to zmienna, pętla, funkcja, rekursja, stos, wskaźnik.

---

## Wymagania techniczne

- **Lua 5.4** zainstalowany lokalnie
- Edytor z podświetleniem składni (VS Code + rozszerzenie Lua, vim z syntax/lua, Neovim)
- Terminal
- Od Modułu 8: kompilator C (`gcc` lub `clang`), `make`, `liblua5.4-dev`

Dla telefonu (Termux na Galaxy A54): wszystko działa, łącznie z kompilacją C — `pkg install lua54 lua54-dev clang make`.

---

## Spis modułów

### Część I: Język

| # | Moduł | Lekcje | Główne pojęcia |
|---|---|---|---|
| 1 | **Fundamenty** | 5 | Setup, REPL, typy, operatory, sterowanie, funkcje |
| 2 | **Tabele** | 5 | Tablice, rekordy, iteracja, biblioteka standardowa |
| 3 | **Funkcje zaawansowane** | 5 | Multiple return, varargs, closures, funkcje wyższego rzędu |
| 4 | **Metatable i OOP** | 6 | `__index`, operatory, klasy, dziedziczenie, weak tables |
| 5 | **Obsługa błędów** | 4 | `error`, `pcall`, `xpcall`, wzorce defensive |
| 6 | **Korutyny** | 5 | Generatory, scheduler, producent-konsument |
| 7 | **Moduły** | 4 | `require`, `package`, prywatny stan, API design |

### Część II: Embedding i KarmazynOS

| # | Moduł | Lekcje | Główne pojęcia |
|---|---|---|---|
| 8 | **C API: podstawy** | 5 | `lua_State`, stos, push/pop, wywołania w obie strony |
| 9 | **Userdata i bindings** | 5 | Light/full userdata, metatable z C, `__gc` |
| 10 | **Sandboxing** | 5 | `_ENV`, hooks, custom alokator, walidacja |
| 11 | **DSL dla KarmazynOS** | 4 | DSL polityk HSS, parser konfiguracji, hot-reload |
| 12 | **Capstone** | 4 | Mini Φ-space scheduler, plugin system, finalna integracja |

---

## Konwencje

W kodzie używam jednolitych konwencji, które warto przenieść do Twojego kodu produkcyjnego:

```lua
-- Zmienne lokalne: snake_case
local atom_count = 0
local phi_threshold = 0.5

-- Stałe-jak: SCREAMING_SNAKE_CASE
local MAX_ATOMS = 1000
local DEFAULT_PHI = 0.0

-- Funkcje: snake_case dla zwykłych, camelCase niedozwolone
local function compute_distance(a, b) ... end

-- Klasy / typy / moduły: PascalCase
local Holon = {}
local PhiSession = {}

-- Metody: snake_case
function Holon:add_atom(atom) ... end
```

**Zawsze `local`.** Globalne zmienne są w tym kursie traktowane jako błąd, chyba że wyraźnie zaznaczone.

**Bez tabulatorów.** Indent = 4 spacje (zgodnie z konwencją Lua-users i większością dużych projektów Lua).

---

## Jak wykonywać zadania

Każde zadanie to plik `.lua`. Załóż folder na ćwiczenia:

```bash
mkdir -p ~/karmazyn/lua_kurs/m01
cd ~/karmazyn/lua_kurs/m01
```

Pisz każde zadanie jako osobny plik, np. `m01_l01_z01.lua`, uruchamiaj:

```bash
lua5.4 m01_l01_z01.lua
```

Po rozwiązaniu zadania **i porównaniu** z rozwiązaniem z kursu, zachowaj plik. Pod koniec kursu będziesz mieć pełną kolekcję ćwiczeń, która sama w sobie jest świetną referencją.

---

## Filozofia: dlaczego Lua

Lua jest **językiem rozszerzania**, nie aplikacyjnym. To znaczy: nie pisze się w Lua całych systemów. Pisze się w C/C++/Rust system, a Lua wstawia się jako warstwę:
- konfiguracji (zamiast YAML/TOML — pełen Turing-complete config)
- skryptów użytkownika (gracze, administratorzy, "techpriesty")
- polityk i reguł biznesowych
- rapid prototyping fragmentów logiki

Dla KarmazynOS to dokładnie pasuje. HSS jako rdzeń pisany w C i Rust ("Sancta Ferrum"), ale polityki Φ-space, hooki sesji, pipeline multi-agent — wszystko to **może być Lua**, kompilowane jednorazowo i wykonywane w sandboxie z ograniczeniami CPU/RAM per session.

Konkurencja:
- **Python** — za duży (~5 MB), za wolny do embeddingu, GIL, brak naturalnego sandboxa.
- **JavaScript (V8/QuickJS)** — V8 to giant; QuickJS jest mały i fajny ale młodszy ekosystem.
- **WASM** — uniwersalny ale potrzebujesz toolchaina po stronie autora skryptu; dla "techpriest pisze polityk" za ciężkie.
- **Rhai, Gluon, Wren** — niszowe, mały ekosystem, nikt ich nie zna.

Lua wygrywa kompromisem: tani interpreter, łatwa składnia, zerowe zależności, sandbox za darmo, 30+ lat dojrzałości.

---

## Status kursu

- [x] Moduł 0: Dla początkujących (opcjonalny)
- [x] Moduł 1: Fundamenty
- [x] Moduł 2: Tabele
- [x] Moduł 3: Funkcje zaawansowane
- [x] Moduł 4: Metatable i OOP
- [x] Moduł 5: Obsługa błędów
- [x] Moduł 6: Korutyny
- [x] Moduł 7: Moduły
- [x] Moduł 8: C API podstawy
- [x] Moduł 9: Userdata i bindings
- [x] Moduł 10: Sandboxing
- [x] Moduł 11: DSL dla KarmazynOS
- [x] Moduł 12: Capstone

---

## Licencja i autorstwo

Kurs powstał jako część dokumentacji **KarmazynOS** w ramach materiałów Schola Mechanica (HollyScriptSanctum extras). Możesz go modyfikować, przepisywać, dostosowywać do własnych potrzeb.

Wszystkie przykłady kodu są w domenie publicznej.

---

*Następny krok: otwórz `M01_fundamenty.md` i zacznij od Lekcji 1.1.*

### Dodatkowe

- [x] Moduł Bonus: KarmazynOS Warp Engine Demo (multi-agent swarm + termodynamika)
