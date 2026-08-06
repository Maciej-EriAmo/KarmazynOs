# KarmazynOS — Bootstrap Stages (from scratch)

**Status:** living · **Data:** 2026-08-06  
**Decyzja architektoniczna:** kanoniczną podstawą systemu jest jądro w Rustcie (rustc + Cargo).

Powiązania: `rust_roadmap_tech.md`, `rust_substrate_map.md`, `runtime_pl.md`, `native/`.

---

## Cel

Zbudować **jednorodne środowisko**, w którym rdzeń KarmazynOS (jądro + Shell + podstawowe narzędzia) da się odtworzyć z jednego, spójnego łańcucha narzędziowego — bez Pythona jako warstwy nośnej.

Analogia do klasycznego bootstrapu Gentoo (stage1 → stage2 → stage3):
nie bierzemy gotowego obrazu, tylko podnosimy istniejącą podstawę do pełnej samodzielności.

Obecny punkt startowy: `native/karmazyn_substrate` + `native/karmazyn_slab` (już działający Store, reach-GC, C ABI).

---

## Stage 1 — Bootstrap (jądro jako niezależna jednostka)

**Cel**  
Rustowe jądro staje się prawdziwym, samodzielnym fundamentem.  
Da się je zbudować, przetestować i uruchomić **bez Pythona**.

**Zakres**
- Pełne prawo systemu w Rustcie: atomy, temperatura, stany (HOT / WARM / COLD / TOMB), reach-GC, podstawowe pryzmaty, tick.
- Stabilne **C ABI** (`ksub_*` i dalsza ewolucja) jako jedyna oficjalna granica binarna.
- Minimalny program testowy (pure Rust lub C), który:
  - otwiera Store,
  - tworzy atomy,
  - wykonuje tick + GC,
  - wypisuje stats.
- Python Store pozostaje wyłącznie jako referencja / golden tests.
- Dokumentacja: jak zbudować jądro od zera na czystym `rustc` + Cargo.

**Kryterium wyjścia**  
Można sklonować repozytorium, wykonać `cargo build --release` w katalogu jądra i otrzymać działające, samodzielne jądro + testy bez zależności od interpretera Pythona w ścieżce krytycznej.

To jest **Bootstrap Level 1**.

---

## Stage 2 — Native Shell + cienki most

**Cel**  
System da się używać bez Pythona. Shell i podstawowe narzędzia rozmawiają bezpośrednio z jądrem.

**Zakres**
- Shell napisany w Rustcie (lub bardzo cienki, kompilowany), korzystający wyłącznie z C ABI / natywnego API jądra.
- Podstawowe komendy: `stats`, tworzenie atomu, `tick`, podgląd stanów, proste zapisanie / odczyt stanu.
- Python staje się **opcjonalnym klientem** (binding przez C ABI lub osobny crate).
- Lua (jeśli zostaje) hostowana na natywnym jądrze, a nie przez warstwę Pythona.
- Możliwość napisania małego zewnętrznego programu w C / Rust, który linkuje się do jądra i działa.

**Kryterium wyjścia**  
Da się uruchomić interaktywną sesję KarmazynOS (shell) na czystym binarnym jądrze.  
Python nie jest wymagany do podstawowej pracy.

---

## Stage 3 — Jednorodne środowisko („KarmazynOS from scratch”)

**Cel**  
Cały rdzeń systemu (jądro + shell + podstawowe narzędzia + proces budowania) tworzy spójne, odtwarzalne środowisko.  
Od minimalnego zestawu narzędzi (`rustc` + Cargo + kilka zależności systemowych) da się zbudować działający KarmazynOS.

**Zakres**
- Oficjalny sposób bootstrapowania: skrypt / proces „from scratch”, który:
  1. buduje jądro,
  2. buduje shell,
  3. instaluje minimalny zestaw narzędzi,
  4. pozwala od razu pracować w jednorodnym środowisku.
- Wyższe warstwy (bindingi Cynober / KarminQL, narzędzia analityczne, ewentualni goście) siedzą czysto *na* tym fundamencie, a nie go zastępują.
- Możliwość dalszego rozwoju (w tym eksperymentów z jakością informacji przy osłabionej kryptografii) bez powrotu do heterogenicznego stosu Python-first.
- Jasna deklaracja w dokumentacji: Stage 3 = system, który sam siebie buduje jako spójną całość na rustowej podstawie.

**Kryterium wyjścia**  
Nowy deweloper / nowa maszyna potrafi, mając tylko `rustc` + Cargo i instrukcję, dojść do w pełni używalnego rdzenia KarmazynOS bez polegania na istniejącym środowisku Pythonowym jako nośniku.

---

## Podsumowanie

| Stage | Nazwa                | Główny efekt                                         | Analogia Gentoo |
|-------|----------------------|------------------------------------------------------|-----------------|
| 1     | Bootstrap            | Samodzielne rustowe jądro + stabilne C ABI           | stage1          |
| 2     | Native Shell         | Praca z systemem bez Pythona                         | stage2          |
| 3     | Homogeneous Core     | Od source do działającego jednorodnego środowiska    | stage3          |

**Dzisiaj (2026-08-06):** jesteśmy na progu Stage 1.  
Istniejący `native/karmazyn_substrate` + `karmazyn_slab` stanowi punkt wyjścia.  
Należy go podnieść do rangi prawdziwego jądra i oderwać od zależności od Pythona w ścieżce krytycznej.

---

## Zasada decyzyjna

Każdy nowy element oceniamy pytaniem:

> Czy da się to zbudować bezpośrednio na rustowym jądrze bez powrotu do Pythona jako warstwy nośnej?

Jeśli nie — nie należy do Bootstrap 1–3.

---

*Dokument żywy. Aktualizacja 2026-08-06.*
