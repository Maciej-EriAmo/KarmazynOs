# KarmazynOS — Runtime (kanon 2026)

**Jądro:** `karmazyn_kernel` v1.1.0  
**Boot:** `karmazyn_boot` v0.5+  
**Gość Lua:** `karmazyn_lua` **1.0.0** (stable; gate: `software/test_lua_release.py`, macierz 26/28)  
**Substrat native (Rust):** faza 0/1 — prawo reach-GC + C ABI  

Ten dokument opisuje **aktualny** runtime monorepo (nie archiwalny `shell.py` / `studio.py` w `archiwum/`).

---

## 1. Co to jest w praktyce

KarmazynOS w trybie boot to **aktywny interpreter na żywym substracie** — w duchu BASIC na ZX Spectrum:

1. Wstaje **Store** (atomy, bąble, korzenie, tick, reach-GC).
2. Montuje się **gość**: domyślnie **Lua** (`LUA/`), albo **mini-Lisp** (`karmazyn_exec`).
3. Działa **scheduler termiczny** (tick w tle) + prompt `karmazyn>`.

Prawo jądra:

> **Temperatura mówi KIEDY. Osiągalność mówi CZY.**  
> zimny + nieosiągalny → Vacuum Decay (GC)  
> zimny + osiągalny → retained TOMB (retencja, nie usunięcie)

---

## 2. Warstwy i szwy

```
┌─────────────────────────────────────────────────────────┐
│  Host: CLI / boot / edytor  (FS, projekt, lua_bin)      │
│    run | check | repl | :project | :run | :reload       │
├─────────────────────────────────────────────────────────┤
│  Gość: Lua  |  mini-Lisp     eval_line(str) → str       │
│  (LUA/, karmazyn_exec)  sandbox = bąbel (bez ambient FS)│
│  package.searchers: preload → memory → project          │
├─────────────────────────────────────────────────────────┤
│  Szwy językowe (rejestr haków Store):                   │
│    register_env_of(fn, name=…)     — domknięcia/tabele  │
│    register_extra_reach(fn, name=) — ramki wywołań      │
│    set_root / unset_root           — korzenie GC        │
├─────────────────────────────────────────────────────────┤
│  Fasada: karmazyn_kernel  (JEDYNE wejście oprogramowania)│
├─────────────────────────────────────────────────────────┤
│  Substrat (implementacja):                              │
│    Python  karmazyn_substrate.Store   ← domyślny boot   │
│    Rust    native/karmazyn_substrate  ← testy / faza N  │
└─────────────────────────────────────────────────────────┘
```

**Zasada:** sandbox gościa = **bąbel**. Host montuje **projekt** (mapa plików →
`require`) i opcjonalnie bufory edytora (memory searcher). Gość **nie** ma
`dofile` / `loadfile` / `package.path` systemowego / `os.execute`.

**Reguła granicy:** jadro **nigdy** nie importuje oprogramowania  
(`python kernel_boundary.py kernel/ software/` → twarda brama).

Gość **nie** grzebie w `_env_of` ręcznie — używa rejestru haków (`name='guest'` = zamiana przy switchu).

---

## 3. Uruchomienie

### Wymagania

- Python 3.10+ (testowane też 3.14)
- opcjonalnie `numpy` (HRR); bez numpy jadro wstaje w trybie zero-dep
- opcjonalnie Rust + MinGW/MSVC do substratu native

### Prompt (żywy system)

```bash
cd KarmazynOs
python karmazyn_boot.py
```

```text
karmazyn> x = 10
karmazyn> return x * 2
20
karmazyn> :help
karmazyn> :stats
karmazyn> :guest exec          # mini-Lisp
karmazyn> (+ 1 2)
karmazyn> :guest lua
```

### Demo

```bash
python karmazyn_boot.py --demo
python karmazyn_boot.py --lisp --demo    # gość mini-Lisp
```

### Projekt Lua (multi-file, host → bąbel)

```bash
# z katalogu repo (boot)
python karmazyn_boot.py --project LUA/examples/hello
# w prompcie:
#   :project          — pokaż root
#   :check            — parse wszystkich *.lua
#   :run              — main.lua
#   :reload util      — odśwież require z dysku
#   return require("lib.greeter").hello("x")

# bez pełnego OS — CLI pakietu
cd LUA
python run_lua.py run examples/hello
python run_lua.py check examples/hello
python run_lua.py path lib.greeter -p examples/hello
python run_lua.py repl examples/hello
python _run_tests.py                  # ~151 testów
python kombajn_run.py                 # kombajn integracyjny
```

### Docker (Alpine, separacja jadro/oprogramowanie)

```bash
docker build -t karmazyn .
docker run -it karmazyn
```

---

## 4. Przełączniki

### Gość (język)

| Sposób | Wartości |
|--------|----------|
| Env `KARMAZYN_GUEST` | `lua` (domyślnie), `exec` / `lisp` |
| CLI | `--lua`, `--lisp` / `--exec`, `--guest NAME` |
| REPL | `:guest`, `:guest lua`, `:guest exec` |

| Env / flaga | Znaczenie |
|-------------|-----------|
| `KARMAZYN_LUA` | katalog pakietu `karmazyn_lua` (preferuj z `project.py`) |
| `KARMAZYN_PROJECT` / `--project PATH` | root projektu → searcher `require` |
| `KARMAZYN_TOOLS` | katalog `*.lua` → `package.preload` |
| `KARMAZYN_LUA_BIN` | katalog narzędzi OS (preload + module root) |

Narzędzia: `software/tools/*.lua` → preload; opcjonalnie monorepo `lua_bin/`.  
CLI pakietu: `LUA/run_lua.py` (`run` \| `check` \| `path` \| `repl`).

### Substrat (jądro implementacji) — na razie głównie testy

| Sposób | Wartości |
|--------|----------|
| Env `KARMAZYN_SUBSTRATE` | `python` (domyślnie), `native`, `both` (tylko testy) |
| CLI (testy) | `--python`, `--native`, `--substrate native` |
| API | `open_store(backend="native"\|"python")` |

```python
from karmazyn_kernel import open_store, kernel_info

s = open_store(backend="python")   # boot path
s = open_store(backend="native")   # wymaga DLL z cargo build --release
print(kernel_info()["substrate"])
```

**Boot produkcyjny** nadal tworzy Python `Store`.  
Native jest **źródłem prawdy dla prawa GC** + golden tests; pełny drop-in w boot = kolejna faza.

---

## 5. Testy

```bash
# Prawo substratu (Python)
python -m unittest test_substrate -v

# Zgodność Python ↔ Rust (+ przełącznik)
python test_substrate_compat.py -v
python test_substrate_compat.py --native -v

# Granica jadro ↛ software
python kernel_boundary.py kernel/ software/

# Rust (wymaga toolchain)
cd native/karmazyn_substrate
cargo test
cargo build --release
python ../../native/karmazyn_substrate_native.py   # smoke z roota: python native/...
```

---

## 6. Mapa katalogów (istotne)

| Ścieżka | Rola |
|---------|------|
| `kernel/` | źródło prawdy jadra Python |
| `software/` | boot, exec, phi |
| `LUA/` | gość Lua (vendored) + host CLI/projekt |
| `LUA/examples/hello/` | demo multi-file (`require`) |
| `lua_bin/` | skrypty narzędzi OS (host montuje jako tools) |
| `native/karmazyn_substrate/` | substrat Rust + C ABI |
| `holo/` | Linux HSS LSM (C) — most bezpieczeństwa, nie mini-runtime |
| `archiwum/` | historyczny monolit (shell/studio…) |
| lustro root `karmazyn_*.py` | import bez `PYTHONPATH` |

Szczegóły native: [../native/README.md](../native/README.md).  
Wersje: [../VERSION.txt](../VERSION.txt).

---

## 7. Komendy OS w prompcie (skrót)

| Komenda | Znaczenie |
|---------|-----------|
| `:help` | kod gościa + lista komend |
| `:info` | wersja jadra, HRR |
| `:stats` | total / HOT…TOMB / reaped / retained_tomb |
| `:tick n` | n ticków ręcznie |
| `:gc` | studzenie + raport |
| `:ls [stan]` | lista atomów |
| `:env` | wiązania korzenia |
| `:tools` | package.preload (Lua) |
| `:project [path]` | root projektu (mapa host→bąbel / `require`) |
| `:run [file]` | uruchom `main.lua` lub plik (host czyta FS) |
| `:reload [mod]` | wyczyść cache `require` / przeładuj moduł |
| `:check [dir]` | parse wszystkich `*.lua` w projekcie |
| `:guest [lua\|exec]` | przełącznik gościa |
| `:exit` | wyjście |

---

## 7b. Gość Lua — status (v1 host+projekt)

| Warstwa | Stan |
|---------|------|
| Język (podzbiór 5.5) + metatabele + liby | ✅ testy unit (~151) + kombajn |
| Tabela = Bubble, reach-GC, kontrakt A–H | ✅ |
| Projekt multi-file, CLI, boot `:project`/`:run` | ✅ |
| Memory searcher (bufor edytora → `require`) | ✅ |
| `strict-project` (run tylko pod rootem) | ✅ |
| Błędy `@plik:linia:kolumna:` (parse) | ✅ |
| Pełne `dofile` / ambient FS | ❌ celowo (sandbox = bąbel) |
| Host API `karmazyn.*` + `:tool` + smoke `lua_bin` | ✅ **1.0.0** (`karmazyn._VERSION`) |
| Macierz `lua_bin` | ✅ 26 pass / 2 skip (top, nano) |
| Reach hooks `register_*` name=guest | ✅ |
| Numery linii parse (+ częściowo runtime) | ✅ |

**Release:** **1.0.0** · tag `lua-v1.0.0` · [../LUA/README.md](../LUA/README.md) · [tools_lua.md](tools_lua.md) · [lua_bin_status.md](lua_bin_status.md).

---

## 8. Native Rust — status

| Faza | Stan |
|------|------|
| 0. Atom/Bubble/tick/reach-GC + C ABI | ✅ |
| 1. Testy zgodności z Python Store | ✅ (`test_substrate_compat`) |
| 2. Pełny drop-in (EventBus, metadata, HRR) | ⏳ |
| 3. Boot na `KARMAZYN_SUBSTRATE=native` | ⏳ |
| 4. Python Store tylko jako referencja | ⏳ |

C dla **holo LSM** zostaje; **substrat** = Rust (ownership grafu GC).
