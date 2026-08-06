# KarmazynOS — Bootstrap Stages (from scratch)

**Status:** living · **Data:** 2026-08-06  
**Decyzja architektoniczna:** kanoniczną podstawą systemu jest jądro w Rustcie (rustc + Cargo).

Powiązania: `rust_roadmap_tech.md`, `rust_substrate_map.md`, `runtime_pl.md`, `native/`.

---

## Cel

Zbudować **jednorodne środowisko**, w którym rdzeń KarmazynOS (jądro + Shell + podstawowe narzędzia) da się odtworzyć z jednego, spójnego łańcucha narzędziowego — bez Pythona jako warstwy nośnej.

Analogia do klasycznego bootstrapu Gentoo (stage1 → stage2 → stage3):
nie bierzemy gotowego obrazu, tylko podnosimy istniejącą podstawę do pełnej samodzielności.

Punkt startowy (i Stage 1 done): `native/karmazyn_substrate` + `native/karmazyn_slab` (Store, reach-GC, C ABI `ksub_*`).

---

## Stage 1 — Bootstrap (jądro jako niezależna jednostka) ✅ DONE

**Cel**  
Rustowe jądro staje się prawdziwym, samodzielnym fundamentem.  
Da się je zbudować, przetestować i uruchomić **bez Pythona**.

**Zakres**
- Pełne prawo systemu w Rustcie: atomy, temperatura, stany (HOT / WARM / COLD / TOMB), reach-GC, tick.
- Stabilne **C ABI** (`ksub_*`) jako jedyna oficjalna granica binarna (`include/karmazyn_substrate.h`).
- Minimalny program testowy (pure Rust **i** C):
  - otwiera Store,
  - tworzy atomy,
  - wykonuje tick + GC,
  - wypisuje stats.
- Python Store pozostaje wyłącznie jako referencja / golden tests.
- Dokumentacja + bramka: `native/stage1_verify.ps1`.

**Kryterium wyjścia** ✅  
Można sklonować repozytorium, wykonać `cargo build --release` w katalogu jądra i otrzymać działające, samodzielne jądro + testy bez zależności od interpretera Pythona w ścieżce krytycznej.

### Jak zbudować Stage 1 (bez Pythona)

```powershell
cd C:\Users\drwis\KarmazynOs

# pełna bramka: slab tests + substrate tests + stage1_bootstrap + C ABI smoke
.\native\stage1_verify.ps1
# bez C:  .\native\stage1_verify.ps1 -SkipC

# ręcznie:
cd native\karmazyn_slab
cargo test --release

cd ..\karmazyn_substrate
cargo test --release
cargo build --release
cargo run --example stage1_bootstrap --release
cargo run --example hello_store --release
```

Artefakty: `native/karmazyn_substrate/target/release/karmazyn_substrate.dll` (Windows) / `.so` / `.dylib` + rlib.

| Deliverable | Ścieżka |
|-------------|---------|
| Host Store + C ABI | `native/karmazyn_substrate` |
| Freestanding slab / reach-GC | `native/karmazyn_slab` |
| Pure Rust gate example | `examples/stage1_bootstrap.rs` |
| C ABI smoke | `native/c_smoke/stage1_c_smoke.c` |
| Verify script | `native/stage1_verify.ps1` |

To jest **Bootstrap Level 1** — zamknięte 2026-08-06.

---

## Stage 2 — Native Shell + cienki most 🚧 IN PROGRESS

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

### Stan (2026-08-06)

| Element | Status |
|---------|--------|
| `native/karmazyn_shell` REPL | ✅ stats/atom/heat/tick/settle/bubble/root/bind/lookup |
| Persist save/load | ✅ `save`/`load` — format `KSUB_SNAP 1` (`Store::export_snapshot`) |
| Batch mode | ✅ `-e "cmd"` / plik skryptu |
| Shell link tylko przez C ABI (nie rlib) | ❌ opcjonalne; dziś rlib (OK dla Stage 2) |
| Lua bez Pythona | ❌ Stage 2+ |
| Python = optional client | ⏳ host nadal Python-first dla boot; shell już bez Pythona |

```powershell
cd native\karmazyn_shell
cargo run --release
# k$ help
# k$ atom var x 50
# k$ bubble root
# k$ root 0
# k$ bind 0 x 0
# k$ save out\demo.ksub
# k$ load out\demo.ksub

# batch (bez interakcji):
cargo run --release -- -e "atom var x 50" -e "bubble r" -e "root 0" -e "bind 0 x 0" -e "save out\demo.ksub" -e quit
```

---

## Stage 3 — Jednorodne środowisko („KarmazynOS from scratch”) 🚧 starter

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

### Stan (2026-08-06)

| Element | Status |
|---------|--------|
| `native/bootstrap_from_scratch.ps1` | ✅ starter: tool-check → Stage1 gate → shell build → save/load smoke |
| Prefiksowa instalacja do `prefix/` | ❌ TODO |
| Linux/mac shell script | ❌ TODO (`bootstrap_from_scratch.sh`) |
| Lua + wyższe warstwy na fundamencie | ❌ poza starterem |

```powershell
# jedyna komenda (wymaga rustc+cargo; Python NIE jest potrzebny)
.\native\bootstrap_from_scratch.ps1
# → STAGE1_VERIFY_OK + shell build + BOOTSTRAP_FROM_SCRATCH_OK
```

---

## Podsumowanie

| Stage | Nazwa                | Główny efekt                                         | Analogia Gentoo | Status |
|-------|----------------------|------------------------------------------------------|-----------------|--------|
| 1     | Bootstrap            | Samodzielne rustowe jądro + stabilne C ABI           | stage1          | ✅ DONE |
| 2     | Native Shell         | Praca z systemem bez Pythona                         | stage2          | 🚧 +persist |
| 3     | Homogeneous Core     | Od source do działającego jednorodnego środowiska    | stage3          | 🚧 starter |

**Dzisiaj (2026-08-06):**  
- Stage 1 ✅ `stage1_verify.ps1`  
- Stage 2 🚧 shell + `KSUB_SNAP` + batch `-e`  
- Stage 3 🚧 `bootstrap_from_scratch.ps1` (starter; brak prefix install / sh)

---

## Zasada decyzyjna

Każdy nowy element oceniamy pytaniem:

> Czy da się to zbudować bezpośrednio na rustowym jądrze bez powrotu do Pythona jako warstwy nośnej?

Jeśli nie — nie należy do Bootstrap 1–3.

---

*Dokument żywy. Aktualizacja 2026-08-06 (Stage 1 gate + shell MVP).*
