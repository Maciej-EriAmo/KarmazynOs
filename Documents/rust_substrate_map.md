# Mapa: Rust na substracie KarmazynOs

**Wersja ABI:** `0.1.0-karmazyn-substrate`  
**Kompilator:** `rustc` (stable) + `cargo`  
**Decyzja kanoniczna:** Rust = implementacja Product Store; Python = referencja / golden.

Powiązania: `native/README.md`, `runtime_pl.md` §substrat, `ARCHITECTURE.pl.md` §5, `io_stage1.md`, **`build_deploy_plan.md`**.

---

## 1. Gdzie Rust siedzi w systemie

```
┌─────────────────────────────────────────────────────────────────┐
│  Studio SDL / shell / Lua guest / I/O thermal (software/)       │  Python
│  karmazyn_boot · karmazyn_io · karmazyn_host · karmazyn_studio  │
├─────────────────────────────────────────────────────────────────┤
│  Fasada jądra: karmazyn_kernel  →  open_store() / Store         │  Python
│  Przełącznik:  karmazyn_backend  (native | python)              │
├─────────────────────────────────────────────────────────────────┤
│  NativeStore  (karmazyn_substrate_native.py)                    │  Python
│    · metadata, EventBus, HRR, string↔int (gdy potrzeba)         │
│    · most: PyO3 CoreStore  LUB  ctypes ksub_*                   │
├──────────────────────┬──────────────────────────────────────────┤
│  PyO3                │  C ABI (cdylib)                          │
│  karmazyn_substrate  │  ksub_*  (ffi.rs + .h)                   │
│  _rs (CoreStore)     │                                          │
├──────────────────────┴──────────────────────────────────────────┤
│                                                                 │
│              ★  RUST: karmazyn_substrate (crate)  ★             │
│         atom.rs · store.rs · ffi.rs · lib.rs                    │
│         prawo T×reach · atomy · bąble · roots · tick · GC       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
         ↑ gość NIE wchodzi tu — tylko haki env_of / extra_reach
```

**Zasada:** Rust **nie zna** Lua, Pythona, SDL, GRUB.  
Zna: **T, atomy, bąble, korzenie, tick, vacuum vs retained TOMB**.

---

## 2. Mapa katalogów / crate

| Ścieżka | Rola | Artefakt |
|---------|------|----------|
| `native/karmazyn_substrate/` | **Rdzeń Rust** (rlib + cdylib) | `libkarmazyn_substrate.*`, `.dll`/`.so` |
| `…/src/lib.rs` | root crate, re-export, `ABI_VERSION` | |
| `…/src/atom.rs` | model atomu, progi T, FSM HOT…TOMB | |
| `…/src/store.rs` | Store: graf, reach walk, tick/settle | |
| `…/src/ffi.rs` | C ABI `ksub_*` | |
| `…/include/karmazyn_substrate.h` | nagłówek C | |
| `native/karmazyn_substrate_rs/` | **PyO3** `CoreStore` | wheel `.whl` |
| `native/karmazyn_substrate_native.py` | drop-in Store dla Pythona | import hosta |
| `kernel/karmazyn_backend.py` | wybór native/python | `open_store` |
| `kernel/karmazyn_substrate.py` | **referencja pure-Python** | golden tests |

**Budowa:**

```text
rustc/cargo  →  native/karmazyn_substrate   (cargo test && cargo build --release)
maturin      →  native/karmazyn_substrate_rs (PyO3 wheel)
```

Skrypt: `native/build_native.ps1` / `.sh`.

---

## 3. Mapa pojęć: ontologia ↔ Rust

| Pojęcie Karmazyn | Typ Rust | Id / handle | Uwagi |
|------------------|----------|-------------|--------|
| Atom | `struct Atom` | `AtomId = u32` | S, E, t, value_token |
| Temperatura T | `f64` w `Atom.t` | — | clamp `[0, T_MAX]` |
| Stan HOT/WARM/COLD/TOMB | `state_for_t(t)` | — | progi jak Python |
| Bubble | `struct Bubble` | `BubbleId = u32` | bindings, parent |
| Store | `struct Store` | — | Mutex wewnątrz |
| Handle C (store) | `u64` 1-based | tabela w `ffi.rs` | opaque dla hosta |
| Payload języka | `value_token: u64` | np. `id(obj)` Python | **opaque** — Rust nie interpretuje |
| Korzeń GC | `roots: Vec<BubbleId>` | — | `set_root` / `unset_root` |
| Retained TOMB | `HashSet<AtomId>` | — | zimny + osiągalny |
| Hak env_of | `EnvOfFn` | token → BubbleId | gość rejestruje |
| Hak extra_reach | `ExtraReachFn` | → `Vec<AtomId>` | ramki / extra |

### Progi T (atom.rs) — wspólne z Python

| Stała | Wartość | Znaczenie |
|-------|---------|-----------|
| `T_INIT` | 50 | start |
| `T_MAX` | 100 | clamp góra |
| `T_HOT` | 70 | ≥ HOT |
| `T_WARM` | 30 | ≥ WARM |
| `T_TOMB` | 2 | &lt; TOMB = dead |
| `DECAY_DEFAULT` | 0.92 | tick |
| `HEAT_READ` | 10 | touch/heat |

---

## 4. Prawo jądra w Rust (store.rs)

```
temperatura  →  KIEDY atom może stać się kandydatem do GC
osiągalność  →  CZY wolno go usunąć

  zimny + nieosiągalny  →  vacuum (reap)     // usunięcie
  zimny + osiągalny     →  retained TOMB     // zostaje w grafie
```

**Walk reach (Rust):**

```
roots
  → bubble.bindings → atom ids
  → bubble.parent chain
  → env_of(value_token) → bubble
  → extra_reach() → atom ids
```

Gość (Lua/Python) **nie** jest w crate — tylko callbacki zarejestrowane z hosta.

---

## 5. Mapa API

### 5.1 Wewnętrzne (Rust, rlib)

| API | Moduł |
|-----|--------|
| `Atom::new / decay / state / is_dead` | `atom` |
| `Store::new / atom_new / heat / tick / settle` | `store` |
| `bubble_new / bind / lookup / set_root` | `store` |
| `register_env_of / register_extra_reach` | `store` |
| `stats` | `store` |

### 5.2 C ABI (`ksub_*`) — szew stabilny

| Symbol | Rola |
|--------|------|
| `ksub_version` | string ABI |
| `ksub_store_new` / `ksub_store_free` | lifetime Store |
| `ksub_atom_new` / `has` / `delete` / `heat` / `atom_t` | atomy |
| `ksub_atom_set_value` / `ksub_atom_value` | opaque token |
| `ksub_bubble_new` / `bind` / `lookup` / `unbind` | bąble |
| `ksub_set_root` / `unset_root` | korzenie |
| `ksub_tick` / `ksub_settle` | termodynamika + GC |
| `ksub_stats` | `KSubStats` |
| `ksub_register_env_of` / `extra_reach` | haki gościa |

Header: `native/karmazyn_substrate/include/karmazyn_substrate.h`.

### 5.3 PyO3 (`CoreStore`)

Cienka powierzchnia: te same operacje co core, bez EventBus/HRR.  
Pełny drop-in: `NativeStore` w Pythonie (nad CoreStore lub ctypes).

### 5.4 Python host (poza Rust)

| Moduł | Co dodaje (nie w Rust) |
|-------|-------------------------|
| `NativeStore` | EventBus, metadata `v`, HRR, proxy atomów |
| `ThermalSurface` | nazwy `io:*` → `AtomId` (int na native) |
| `karmazyn_lua` | eval, tabele = bąble, haki reach |
| Studio SDL | paint/input — zero w crate |

---

## 6. Mapa identyfikatorów (ważne!)

| Warstwa | Id atomu | Uwaga |
|---------|----------|--------|
| **Rust core** | `u32` od 0 | kanon native |
| **C ABI** | `uint32_t` | to samo |
| **PyO3 CoreStore** | `u32` | to samo |
| **Python reference Store** | string `a0`, `a1`… **lub** jawne id | golden |
| **Thermal I/O Stage 1** | `name_to_aid`: `"io:console"` → `u32` na native | tabela hosta |
| **Luneta** | string id + bridge | `luneta_native_bridge` |

**Błąd historyczny (naprawiony Stage 1):** zakładanie string id w Rust → `ValueError` / cichy FAIL.  
**Reguła:** logiczne nazwy żyją w **Pythonie**; w Rust tylko `u32`.

---

## 7. Mapa mostów (jak host woła Rust)

```
open_store(backend="native")
    │
    ├─► PyO3 (preferowane)
    │     karmazyn_substrate_rs.CoreStore
    │         └── Store (Rust, in-process)
    │
    └─► ctypes (fallback)
          karmazyn_substrate.dll / .so
              ksub_store_new → handle u64
              ksub_atom_new(handle, …) → u32
```

Env:

| Zmienna | Znaczenie |
|---------|-----------|
| `KARMAZYN_SUBSTRATE=native` | Product default (gdy most jest) |
| `KARMAZYN_SUBSTRATE=python` | referencja |
| `KARMAZYN_NATIVE_BRIDGE=pyo3\|ctypes` | wybór mostu |

---

## 8. Mapa odpowiedzialności: co W Rust / co POZA

| W Rust (substrate) | Poza Rust |
|--------------------|-----------|
| Atom S/E/T, heat, decay | Treść semantyczna ML / HRR wektory (opc.) |
| Bubble bindings, parent | Lua evaluator, package.preload |
| Roots, reach walk, GC | Shell meta `:io` `:hot` |
| tick / settle / stats | Studio SDL, pygame |
| value_token opaque | mapowanie token → obiekt Python |
| env_of / extra_reach hooks | implementacja haków gościa |
| C ABI + (via PyO3) | BootLog, BootConfig (plan) |
| — | GRUB, VESA, serial early (plan Tor B) |

---

## 9. Mapa toolchain

```
                    rustup
                      │
                   rustc stable
                      │
         ┌────────────┼────────────┐
         ▼            ▼            ▼
   host GNU/MSVC   cargo build   cargo test
   (link.exe|gcc)  --release     (prawo GC)
         │            │
         │            ▼
         │     cdylib + rlib
         │            │
         │     ┌──────┴──────┐
         │     ▼             ▼
         │  .dll/.so      rlib → PyO3 crate
         │     │             │
         │     ctypes      maturin wheel
         │     │             │
         └─────┴──────┬──────┘
                      ▼
              NativeStore / open_store
                      ▼
           boot · thermal · Lua · Studio
```

**Kompilator konieczny Product:** `rustc`.  
**Nie** gcc na substracie (wyjątek: `holo/*.c` LSM).

---

## 10. Mapa ścieżek boota (Rust w środku)

```
start.py / karmazyn_boot
    → kernel_info()
    → open_store(thermal=True)     # → NativeStore jeśli Rust zbudowany
    → attach_thermal(store)        # atomy io:* jako u32 na native
    → mount_evaluator (Lua)
    → shell / REPL  lub  --studio (SDL na tle mapy T)
```

Tor B (przyszłość):

```
GRUB → kentry (Rust freestanding) → ten sam Store crate (no_std ewolucja)
```

Dziś crate jest **`std`** — freestanding = osobna faza, ta sama ontologia.

---

## 11. Mapa testów / bram

| Test | Co weryfikuje względem Rust |
|------|-----------------------------|
| `cargo test` w `karmazyn_substrate` | prawo GC w czystym Rust |
| `test_substrate_compat.py` | Python ↔ Rust golden |
| `test_io_thermal.IoThermalNative` | matryca I/O na int ids |
| `software/test_host_tools` | host na **python** (string ids tools) |
| `native/run_native.ps1` | smoke end-to-end |

---

## 12. Jedna mapa „pamięć” — skrót operatorski

```
RUST substrate
  ├── Atom(u32):  S, E, T, token
  ├── Bubble(u32): bindings → AtomId, parent
  ├── roots[]
  ├── tick: decay → reach → vacuum | retained_tomb
  └── FFI: ksub_* | PyO3 CoreStore

HOST (Python)
  ├── NativeStore: EventBus, metadata, HRR?
  ├── name_to_aid (io:console → u32)
  ├── Lua guest + reach hooks
  └── Studio: mapa T tło, prompt okno
```

---

## 13. Freeze decyzji

| Pytanie | Odpowiedź |
|---------|-----------|
| Język substratu Product? | **Rust** |
| Kompilator? | **`rustc` + cargo** |
| Referencja / golden? | Python `karmazyn_substrate.py` |
| Id w core? | **`u32`** |
| Czy Rust zna Lua/SDL? | **Nie** |
| Czy można wymienić Rust na C w core? | **Nie** bez nowej decyzji kanonicznej |

### 13.1 Z0 — Rust pisze **od razu** pod substrat

Źródło prawdy prawa T×reach×GC = **`native/karmazyn_substrate`**.  
Nie: Python first → port.  
Tak: **Rust substrate first** → `cargo test` → FFI/PyO3 → golden Python → host.

```
feature jądra  →  atom.rs / store.rs  →  cargo test
                      ↓
              ksub_* / CoreStore (szew)
                      ↓
         NativeStore / thermal / boot / studio
```

Szczegóły i punkty sukcesu SZ0.*: **`build_deploy_plan.md` §1.1**.

---

*Dokument mapy — aktualizować przy zmianie ABI (`ABI_VERSION`) lub podziale crate (np. `no_std` kentry).*
