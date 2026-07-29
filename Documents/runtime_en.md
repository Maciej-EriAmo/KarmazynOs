# KarmazynOS — Runtime (canonical 2026)

**Kernel:** `karmazyn_kernel` v1.1.0  
**Boot:** `karmazyn_boot` v0.5  
**Native substrate (Rust):** phase 0/1 — reach-GC law + C ABI  
**Lua guest:** project host layer (multi-file `require`, CLI, memory overlay)

This document describes the **current** monorepo runtime (not archived `shell.py` / `studio.py` under `archiwum/`).  
Full Polish guide: **[runtime_pl.md](runtime_pl.md)**.

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

**Guest sandbox = bubble.** The host maps a project tree into `require`; the guest has no ambient FS (`dofile` / system `package.path` / `os.execute` are absent by design).

---

## Seams

```
Host CLI / boot / editor  (FS, project, lua_bin)
        │
        v
Guest (Lua | mini-Lisp)  --eval_line-->  software
  package.searchers: preload → memory → project
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
python karmazyn_boot.py
python karmazyn_boot.py --demo
python karmazyn_boot.py --lisp --demo
python karmazyn_boot.py --project LUA/examples/hello
```

In the prompt (Lua guest + project):

```text
karmazyn> :project
karmazyn> :check
karmazyn> :run
karmazyn> :reload util
```

Standalone package CLI (no full OS):

```bash
cd LUA
python run_lua.py run examples/hello
python run_lua.py check examples/hello
python run_lua.py repl examples/hello
python _run_tests.py
```

| Switch | Meaning |
|--------|---------|
| `KARMAZYN_GUEST` / `--lua` / `--lisp` | guest language |
| `KARMAZYN_PROJECT` / `--project` | project root for `require` |
| `KARMAZYN_LUA` | path to `karmazyn_lua` package |
| `KARMAZYN_TOOLS` | `*.lua` → `package.preload` |
| `KARMAZYN_LUA_BIN` | OS tool scripts (preload + module root) |
| `KARMAZYN_SUBSTRATE` | `python` \| `native` (tests / `open_store`) |

Boot still uses **Python Store** by default for interactive work.

---

## Tests

```bash
python -m unittest test_substrate -v
python test_substrate_compat.py -v
python kernel_boundary.py kernel/ software/
cd LUA && python _run_tests.py
cd native/karmazyn_substrate && cargo test && cargo build --release
```

Package notes: [../LUA/README.md](../LUA/README.md) · Native: [../native/README.md](../native/README.md).
