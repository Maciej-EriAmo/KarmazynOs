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
| `atom.rs` / `store.rs` / `ffi.rs` | ✅ `std`, 0 deps crates.io |
| `cargo test` | ✅ ~7 testów prawa GC |
| PyO3 `CoreStore` | ✅ most hosta |
| `u32` AtomId / BubbleId | ✅ |
| `no_std` | ❌ nie zaczęte w substrate |
| `boot/kentry` | 🚧 szkielet Multiboot2 + serial OK string |
| Alokator freestanding | 📋 tylko w tym dokumencie (§4) |

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

- [ ] MAX_ATOMS / MAX_BUBBLES ustalone  
- [ ] bump lub slab w osobnym module `alloc_k`  
- [ ] test host (std) tego samego layoutu slotów **albo** mirror w `cargo test`  
- [ ] kentry już drukuje marker (R2)

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
cargo test --manifest-path native/karmazyn_substrate/Cargo.toml
python scripts/dry_run_l1.py

# kentry (gdy target zainstalowany)
rustup target add x86_64-unknown-none
cargo build --manifest-path boot/kentry/Cargo.toml --target x86_64-unknown-none --release
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
| **SR.5** | (G) atom/tick/stats bez CPython |

---

*Aktualizować przy domknięciu R2–R5 (data + tag).*
