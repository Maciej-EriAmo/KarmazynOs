# KarmazynOS — Quick Start

**Time to read: ~5 minutes**  
**Requirements: Python 3.10+** (optional `numpy` for HRR)

| Component | Version |
|-----------|---------|
| Kernel | `karmazyn_kernel` **1.1.0** |
| Lua guest | **`karmazyn_lua 0.8.0-alpha`** |
| Boot | `karmazyn_boot` v0.5+ |

Full guide (PL): **[runtime_pl.md](runtime_pl.md)** · EN: **[runtime_en.md](runtime_en.md)** · tools: **[tools_lua.md](tools_lua.md)** · package: **[../LUA/README.md](../LUA/README.md)**

---

## Install

```bash
git clone https://github.com/Maciej-EriAmo/KarmazynOs
cd KarmazynOs
pip install numpy          # optional
```

**Canonical Lua tree:** monorepo `LUA/` (do not rely on sibling copies).

---

## 1. Boot

```bash
python karmazyn_boot.py
python karmazyn_boot.py --demo
python karmazyn_boot.py --project LUA/examples/hello
python karmazyn_boot.py --lisp
```

```text
karmazyn> x = 10
karmazyn> return x * 2
karmazyn> :tool ls
karmazyn> :help
```

Guest sandbox = **bubble** (no ambient FS). Host injects project files and `karmazyn.*`.

---

## 2. Multi-file project

```bash
cd LUA
python run_lua.py run examples/hello
python run_lua.py check examples/hello
```

---

## 3. Alpha release gate

```bash
python software/test_lua_release.py
# expect: RELEASE GATE OK  karmazyn_lua 0.8.0-alpha
```

---

## Status

**0.8.0-alpha** — usable guest + project host + tool smoke.  
Not full PUC-Rio Lua 5.5. Not 0.9 yet (see `LUA/README.md` Known limits).

Legacy ksh → `archiwum/`.
