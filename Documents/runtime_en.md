# KarmazynOS — Runtime (canonical 2026)

**Kernel:** `karmazyn_kernel` v1.1.0  
**Boot:** `karmazyn_boot` v0.5  
**Native substrate (Rust):** phase 0/1 — reach-GC law + C ABI  

This document describes the **current** monorepo runtime (not archived `shell.py` / `studio.py` under `archiwum/`).

---

## Mental model

Boot is a **live interpreter on a living substrate** (ZX Spectrum BASIC energy):

1. **Store** starts (atoms, bubbles, roots, tick, reach-GC).
2. A **guest** mounts: default **Lua** (`LUA/`), or **mini-Lisp** (`karmazyn_exec`).
3. A **thermal scheduler** ticks in the background; you type at `karmazyn>`.

Kernel law:

> **Temperature says WHEN. Reachability says WHETHER.**  
> cold + unreachable → vacuum GC  
> cold + reachable → retained TOMB

---

## Seams

```
Guest (Lua | mini-Lisp)  --eval_line-->  software
         | register_env_of / extra_reach / set_root
         v
   karmazyn_kernel facade
         v
   Store: Python (default boot)  |  Rust native (tests / next phase)
```

- Kernel never imports software (`kernel_boundary.py`).
- Guests register hooks by **name** (`guest` = replace on switch).

---

## Run

```bash
python karmazyn_boot.py              # interactive
python karmazyn_boot.py --demo
python karmazyn_boot.py --lisp --demo
```

Guest switch: `KARMAZYN_GUEST`, `--lua` / `--lisp`, REPL `:guest lua|exec`.

Substrate switch (tests / `open_store`): `KARMAZYN_SUBSTRATE=python|native`,  
`--python` / `--native`, `open_store(backend=...)`.

Boot still uses **Python Store** by default.

---

## Tests

```bash
python -m unittest test_substrate -v
python test_substrate_compat.py -v
python kernel_boundary.py kernel/ software/
cd native/karmazyn_substrate && cargo test && cargo build --release
```

Full Polish guide: [runtime_pl.md](runtime_pl.md) · Native: [../native/README.md](../native/README.md).
