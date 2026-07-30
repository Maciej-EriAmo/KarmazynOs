# KarmazynOS — Szybki Start

**Czas czytania: ~5 minut**  
**Potrzebujesz: Python 3.10+** (opcjonalnie `numpy` dla HRR)

| Składnik | Wersja |
|----------|--------|
| Jądro | `karmazyn_kernel` **1.1.0** |
| Gość Lua | **`karmazyn_lua 0.8.0-alpha`** |
| Boot | `karmazyn_boot` v0.5+ |

Pełny runtime: **[runtime_pl.md](runtime_pl.md)** · narzędzia Lua: **[tools_lua.md](tools_lua.md)** · pakiet: **[../LUA/README.md](../LUA/README.md)**

---

## Instalacja

```bash
git clone https://github.com/Maciej-EriAmo/KarmazynOs
cd KarmazynOs
pip install numpy          # opcjonalne — bez numpy jadro też wstanie
```

**Źródło Lua:** katalog monorepo `LUA/` (nie polegaj na sibling-kopiach).

---

## 1. Start systemu (kanon)

```bash
python karmazyn_boot.py
```

```text
KarmazynOS — sekwencja startowa
  [ OK ] fasada jadra — v1.1.0 …
  [ OK ] warstwa wykonawcza — gosc=lua, korzen=tak
  [ OK ] host API — global karmazyn.*
karmazyn>
```

### Pierwsze linie

```text
karmazyn> x = 10
karmazyn> return x * 2
20
karmazyn> :help
karmazyn> :stats
karmazyn> :tool ls
```

Demo bez interakcji:

```bash
python karmazyn_boot.py --demo
python karmazyn_boot.py --lisp --demo    # mini-Lisp zamiast Lua
```

---

## 2. Projekt wieloplikowy (host → bąbel)

```bash
python karmazyn_boot.py --project LUA/examples/hello
```

```text
karmazyn> :check
karmazyn> :run
karmazyn> return require("lib.greeter").hello("x")
```

Albo CLI pakietu:

```bash
cd LUA
python run_lua.py run examples/hello
python run_lua.py check examples/hello
```

**Sandbox = bąbel:** gość nie ma dysku; host montuje projekt i `karmazyn.*`.

---

## 3. Narzędzia OS (`lua_bin`)

```text
karmazyn> :tool              # lista
karmazyn> :tool whoami
karmazyn> :tool step
karmazyn> :tool kedit
```

API hosta: [tools_lua.md](tools_lua.md).

---

## 4. Bramka alpha (przed „działa u mnie”)

```bash
python software/test_lua_release.py
```

Powinno zakończyć się: `RELEASE GATE OK  karmazyn_lua 0.8.0-alpha`.

Osobno:

```bash
cd LUA && python _run_tests.py
cd software && python test_host_tools.py -v
```

---

## 5. Status 0.8.0-alpha (uczciwie)

| Jest | Nie jest / limity |
|------|-------------------|
| Gość Lua + GC na Bubble | Pełna Lua 5.5 |
| Projekty, CLI, boot | Ambient FS / dofile |
| `karmazyn.*` + `:tool` + smoke | Stabilne API do 1.0 (alpha = breaking OK) |
| Known limits w `LUA/README.md` | Wszystkie pliki `lua_bin` w smoke |

Droga: **alpha → 0.9** (smoke większości tools + stabilniejszy surface) → **1.0**.

---

## Archiwum

Historyczny `shell.py` / ksh → **`archiwum/`**.  
Kanon 2026: `karmazyn_boot.py` + `kernel/` + `LUA/`.
