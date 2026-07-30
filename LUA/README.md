# karmazyn_lua **0.8.0-alpha**

Interpreter Lua **5.5 (podzbiór)** na substracie KarmazynOS.

| | |
|--|--|
| **Status** | **alpha** — używalny w bootcie i CLI; API hosta może się jeszcze rozszerzać |
| **Sandbox** | **bąbel** — brak ambient FS (`dofile` / system `package.path` / `os.execute`) |
| **Źródło kanoniczne** | `KarmazynOs/LUA/` (monorepo) |
| **Regresja** | `python software/test_lua_release.py` |

## Szybki start

```bash
# z monorepo KarmazynOs
python karmazyn_boot.py
python karmazyn_boot.py --project LUA/examples/hello
python karmazyn_boot.py --demo

# CLI pakietu (bez pełnego OS)
cd LUA
python run_lua.py run examples/hello
python run_lua.py check examples/hello
python run_lua.py repl examples/hello

# bramka alpha
cd ..
python software/test_lua_release.py
```

W prompcie:

```text
karmazyn> x = 10
karmazyn> return x * 2
karmazyn> :tool ls
karmazyn> :project
karmazyn> :help
```

## Architektura host → bąbel

| Warstwa | Rola |
|---------|------|
| Host (CLI / boot / `EditorBridge`) | FS, projekt, `lua_bin` |
| `package.searchers[1]` preload | tools / lua_bin |
| `package.searchers[2]` memory | bufory edytora |
| `package.searchers[3]` project | pliki pod rootem |
| Gość Lua | `require` / `load` / eval |

## API publiczne (Python)

```python
from karmazyn_lua import __version__, mount, mount_session, GuestSession
print(__version__)  # 0.8.0-alpha
```

## Known limits (alpha)

1. **Nie jest** pełną Lua 5.5 / PUC-Rio — podzbiór celowy.
2. **Brak** `dofile` / `loadfile` / ambient `io.open` / `os.execute` (sandbox).
3. **`generate_from_idea`** — wektor placeholder, nie pełny PCA hologramów.
4. **Agenci / hologramy** — rejestr sesji hosta, nie pełny runtime agentowy z paperów.
5. **`lua_bin`:** **26/28 pass** smoke; **skip:** `top` (pętla), `nano` (edytor interaktywny) — macierz: [../Documents/lua_bin_status.md](../Documents/lua_bin_status.md).
6. **Linie w błędach** — mocne na parse; runtime zależy od ścieżki `error()`.
7. **API `karmazyn.*`** — surface `1.0.0-alpha` (`karmazyn._VERSION`), breaking OK do 0.9.
8. **Dryf sibling `C:\Users\…\LUA`** — kanon to monorepo; sibling tylko cache dev.

## Do 0.9

- [x] smoke / status matrix `lua_bin` (26 pass / 2 skip)
- [x] `karmazyn._VERSION` + gate `test_lua_release.py`
- [ ] opcjonalnie: `nano`/`top` w kontrolowanym trybie testowym lub DEPRECATED w man

## Host API i narzędzia

Boot instaluje global `karmazyn` (`software/karmazyn_host.py`).

```text
karmazyn> :tool ls
```

Szczegóły: [../Documents/tools_lua.md](../Documents/tools_lua.md).

## Flagi CLI

| Flaga | Znaczenie |
|-------|-----------|
| `--project` / `-p` | root projektu |
| `--tools` | katalog preload |
| `--lua-bin` | tools + module root |
| `--strict-project` / `--no-strict-project` | run tylko pod rootem |
| `--caps` | `default` \| `strict` \| `compute` \| `full` |

## Testy

| Komenda | Co |
|---------|-----|
| `LUA/_run_tests.py` | unit (~151) |
| `LUA/kombajn_run.py` | kombajn integracyjny |
| `software/test_host_tools.py` | host + tools smoke (12) |
| `software/test_lua_release.py` | **bramka alpha** (wszystko razem) |

Zasada Karmazynu: **bezpieczeństwo na granicy bąbla**, nie w magii ścieżek OS.
