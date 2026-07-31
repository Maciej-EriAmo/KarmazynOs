# Rust — roadmapa techniczna (substrat → kentry)

**Status:** living · **Data:** 2026-07-31  
**Z0:** prawo T×reach×GC tylko w `native/karmazyn_substrate` (najpierw Rust).  
**Nie mylić:** L1 host (DLL + Python) ≠ L4 cold-boot bez CPython.

Powiązania: `rust_substrate_map.md`, `build_deploy_plan.md` §F–G, `native/README.md`.

---

## 1. Warstwy ewolucji crate

```
┌─────────────────────────────────────────────────────────────┐
│  DZIŚ (L1) — std Store                                      │
│  native/karmazyn_substrate  (std, HashMap, Mutex, String)   │
│  + PyO3 / ctypes → host Python                              │
└──────────────────────────┬──────────────────────────────────┘
                           │ feature flags / wydzielenie core
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  P1 — core + alloc (przygotowanie, wciąż host-testowalne)   │
│  lib: atom/store bez std::collections::HashMap (opcjonalnie)│
│  default = std (backward compatible)                        │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  L3 F — kentry (osobny crate)                               │
│  boot/kentry: no_std, Multiboot2, serial marker             │
│  NIE linkuje jeszcze pełnego Store (MVP)                    │
└──────────────────────────┬──────────────────────────────────┘
                           │ po SF.* + design alokatora
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  L4 G — Store na kentry                                     │
│  rlib core + bump/arena + SerialIo (IoPort kontrakt)        │
│  atom/tick/stats na serialu · bez CPython                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Stan dziś (fakt)

| Element | Stan |
|---------|------|
| `atom.rs` / `store.rs` / `ffi.rs` | ✅ `std`; thermal const z `karmazyn_slab` |
| `cargo test` | ✅ slab **12** + substrate Store **7** + reexport smoke |
| PyO3 `CoreStore` | ✅ most hosta |
| `u32` AtomId / BubbleId | ✅ |
| `native/karmazyn_slab` | ✅ R5 — `no_std`, BumpAlloc, SlabStore, reach-GC |
| `slab` re-export w substrate | ✅ ten sam crate co kentry |
| `features default=["std"]` | ✅ R4 |
| `boot/kentry` | ✅ R5: marker + cmdline + `SLAB_OK` stats |
| QEMU serial SF.2 | ⏳ brak qemu w PATH na host dev (opcjonalnie) |
| Store freestanding full GC | ❌ G — host HashMap Store nadal osobny |

---

## 3. Kolejność prac (obowiązkowa)

| Krok | Deliverable | Gate sukcesu |
|------|-------------|--------------|
| **R0** | Utrzymać Z0 + L1 gate | `cargo test` + `dry_run_l1` |
| **R1** | Ten dokument + scoreboard L1 | docs |
| **R2** | `boot/kentry` buduje ELF (target `x86_64-unknown-none` lub dokumentowany cross) | `KARMAZYN_KENTRY_OK` w źródle / QEMU gdy dostępne |
| **R3** | Notatka alokatora + ograniczenia String/HashMap | review przed G |
| **R4** | (opc.) `substrate` feature `std` default | `cargo test --features std` |
| **R5** | kentry linkuje **minimalny** tick stub lub cienki subset Store | serial stats |
| **R6** | Pełne prawo GC freestanding = faza G planu | SG.* |

**Zakaz:** nie startować R5/R6 bez R3 (alokator).  
**Wolno wcześnie:** R2 kentry marker — nie psuje Z0.

---

## 4. Szkic alokatora (zanim G)

### MVP (bump)

```
static mut HEAP: [u8; N] = [0; N];
// bump pointer; brak free (albo tylko arena reset przy panic/halt)
```

Wystarczy na: tablice atomów o **stałym limicie** (np. MAX_ATOMS=4096), nie na nieskończony HashMap.

### Identyfikatory

- Zostaje **`u32`**.  
- Brak `String` w hot path freestanding: S/E jako **stałe bufory** `[u8; MAX_S]` / intern pool **albo** na L4-MVP tylko numeryczne etykiety + serial hex.

### Mapa struktur (cel)

| std dziś | freestanding docelowo |
|----------|------------------------|
| `HashMap<AtomId, Atom>` | `slab` / tablica slotów + free-list |
| `String` w Atom.s/e | fixed array lub pool |
| `Mutex` | single-core: brak lub spin |
| `Vec` grow | prealloc / bump |

### Kryterium „wolno zaczynać G”

- [x] MAX_ATOMS / MAX_BUBBLES ustalone (`karmazyn_slab`: 256 / 64 — stack-safe; static mut na target)  
- [x] bump + slab (`BumpAlloc`, `SlabStore`) w crate `native/karmazyn_slab`  
- [x] test host: `cargo test` slab + substrate  
- [x] kentry drukuje marker (R2)  
- [x] **reach-GC na slab** (root retain / orphan vacuum / env_bubble / unset_root)  
- [x] **kentry linkuje `SlabStore` (R5)** — serial `SLAB_ATOMS` / `REAPED` / `LIVE` / `SLAB_OK`  
- [ ] QEMU potwierdza serial (SF.2) — opcjonalne przed G, zalecane  


### Dług (aktywny)

| Dług | Status |
|------|--------|
| Stack size `SlabStore` | złagodzony mniejszymi MAX_*; freestanding → `static mut` |
| `Store` (HashMap) vs `SlabStore` dual path | zamierzone do G |
| QEMU SF.2 | brak qemu w PATH dev |
| Brak reach hooks dynamicznych na slab | `env_bubble` fixed zamiast callback |
| Bubble auto-vacuum | brak — tylko `bubble_drop` / `reset` (atomy freelist OK) |
| `BumpAlloc` nie zasilany przez SlabStore | API osobno; store = fixed tables |
| Golden T×reach Store vs SlabStore | brak wspólnego scenariusza testowego |
| f64 w freestanding | SSE2 na x86_64; soft-float nie wymuszony |

---

## 5. ABI i wersjonowanie

| Artefakt | Zasada |
|----------|--------|
| `ABI_VERSION` string | bump przy breaking `ksub_*` |
| `Cargo.toml` version | semver crate |
| Header `karmazyn_substrate.h` | ręcznie sync z `ffi.rs` (później cbindgen) |
| CI | `cargo test` substrate na PR (już gate.yml) |

**Breaking =** zmiana layoutu `KSubStats`, semantyki tick, usunięcie symbolu `ksub_*`.

---

## 6. Czego **nie** robić w Rust (plan)

| Nie | Dlaczego |
|-----|----------|
| Port Lua/Studio do Rust „bo szybciej” | puchnie core; Z0 łamie się mentalnie |
| GC logika w `NativeStore.py` | anty-Z0 |
| Pełny HashMap no_std bez limitu | nierealne na bump |
| Twierdzić „mamy OS” po samym kentry marker | L3 ≠ L4 |

---

## 7. Komendy (dev)

```bash
# L1 / Z0
cargo test --manifest-path native/karmazyn_slab/Cargo.toml
cargo test --manifest-path native/karmazyn_substrate/Cargo.toml
python scripts/dry_run_l1.py

# kentry (gdy target zainstalowany)
rustup target add x86_64-unknown-none
cargo build --manifest-path boot/kentry/Cargo.toml --target x86_64-unknown-none --release
# ELF musi zawierać KARMAZYN_KENTRY_OK + SLAB_OK
# QEMU: patrz boot/kentry/README.md
```

---

## 8. Punkty sukcesu (Rust-only)

| ID | Sukces |
|----|--------|
| **SR.1** | L1 dry-run + cargo test zielone (ciągłe) |
| **SR.2** | `boot/kentry` w repo; marker string w bin/src |
| **SR.3** | Doc alokatora (§4) zaakceptowany przed G |
| **SR.4** | QEMU: serial `KARMAZYN_KENTRY_OK` (gdy toolchain OK) |
| **SR.5** | (G) atom/tick/stats bez CPython — **R5 partial:** kentry `SLAB_OK` bez CPython |

---

*Aktualizacja 2026-07-31: R5 — `native/karmazyn_slab` + kentry link.*  
*Recenzja+fix: freelist po vacuum, uczciwy `SLAB_OK`, vacuum+retain demo.*
