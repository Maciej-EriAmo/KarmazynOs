# Native KarmazynOS substrate (Rust)

**Decision: Rust**, not C, for the substrate core.

| Why Rust | Why not C (for this layer) |
|----------|----------------------------|
| Reach-GC graph is ownership-heavy (UAF risk in C) | C still wins for `holo/*.c` Linux LSM |
| Fearless concurrency around `tick` + hooks | Python already has the guest; we need a safe core |
| Clean `cdylib` C ABI for Python/other hosts | Dual language only where needed |

Python guests (Lua / mini-Lisp) stay on the **seams**:
`register_env_of` / `register_extra_reach` / `eval_line`.  
This crate owns: **atoms, bubbles, roots, tick, vacuum vs retained TOMB**.

## Layout

```
native/
  karmazyn_substrate/     # Rust crate (rlib + cdylib)
    Cargo.toml
    src/{lib,atom,store,ffi}.rs
  karmazyn_substrate_native.py   # ctypes loader + smoke
  README.md
```

## Build

Requires [Rust](https://rustup.rs/) (stable).

```bash
cd native/karmazyn_substrate
cargo test
cargo build --release
```

Artifact (Windows): `target/release/karmazyn_substrate.dll`  
Linux: `libkarmazyn_substrate.so` · macOS: `libkarmazyn_substrate.dylib`

## Smoke (Python)

```bash
# from repo root, after cargo build --release
python native/karmazyn_substrate_native.py
```

## Compatibility tests + substrate switch

```bash
# both backends (default when running the compat suite)
python test_substrate_compat.py -v

# only Python / only native
python test_substrate_compat.py --python -v
python test_substrate_compat.py --native -v
# or:
set KARMAZYN_SUBSTRATE=native
python test_substrate_compat.py -v
```

API (also re-exported from `karmazyn_kernel`):

```python
from karmazyn_backend import open_store, substrate_backend, native_available

s = open_store(thermal=True)                 # env KARMAZYN_SUBSTRATE
s = open_store(backend="native")             # force Rust
s = open_store(backend="python")             # force Python
```

Boot still defaults to **Python** `Store`. The switch is for tests and experiments.

## C ABI (stable seam)

| Symbol | Role |
|--------|------|
| `ksub_version` | ABI string |
| `ksub_store_new` / `ksub_store_free` | Store lifetime |
| `ksub_atom_new` / `ksub_has_atom` / `ksub_delete_atom` / `ksub_heat` | Atoms |
| `ksub_bubble_new` / `ksub_bind` / `ksub_lookup` | Bubbles |
| `ksub_set_root` / `ksub_unset_root` | Roots |
| `ksub_tick` / `ksub_settle` / `ksub_stats` | Thermodynamics + GC |
| `ksub_register_env_of` / `ksub_register_extra_reach` | Language hooks |

Language payloads are **opaque `u64` tokens** (e.g. `id(py_obj)`).  
The core never interprets Lua/Python values — only calls host hooks.

## Migration plan

| Phase | Status |
|-------|--------|
| 0. Rust core + C ABI + unit tests (law) | **this tree** |
| 1. Build on CI; golden tests vs Python `test_substrate` | next |
| 2. PyO3 / full `Store` drop-in (events, `metadata["v"]`, HRR optional) | next |
| 3. Boot flag `KARMAZYN_SUBSTRATE=native` | next |
| 4. Pure-Python substrate as reference / fallback only | later |

Until phase 2–3, **production boot still uses Python `karmazyn_substrate`**.  
Native is the new **source of truth for the law**, growing behind the same seams.
