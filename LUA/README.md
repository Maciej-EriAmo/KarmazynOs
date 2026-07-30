# karmazyn_lua **0.9.0**

Interpreter Lua **5.5 (podzbiór)** na substracie KarmazynOS — **domyślny gość skryptowy**.

| | |
|--|--|
| **Status** | **0.9.0** — używalny na co dzień w bootcie, projektach i `:tool` |
| **Sandbox** | **bąbel** — brak ambient FS |
| **Źródło kanoniczne** | `KarmazynOs/LUA/` |
| **Regresja** | `python software/test_lua_release.py` |
| **Macierz tools** | 26 pass / 2 skip (`top`, `nano`) — [lua_bin_status.md](../Documents/lua_bin_status.md) |

## Szybki start

```bash
# monorepo KarmazynOs
python karmazyn_boot.py
python karmazyn_boot.py --project LUA/examples/hello
python software/test_lua_release.py

cd LUA
python run_lua.py run examples/hello
```

```text
karmazyn> return _VERSION          -- etykieta zgodności Lua 5.5
karmazyn> :tool ls
karmazyn> :tool whoami
```

## Architektura

| Warstwa | Rola |
|---------|------|
| Host | CLI / boot / `EditorBridge` — FS, projekt, `lua_bin` |
| searchers | preload → memory → project |
| Gość | eval / `require` / `load` — bez `dofile` |
| `karmazyn.*` | host API (`software/karmazyn_host.py`, `karmazyn._VERSION`) |

## Known limits (0.9)

1. Podzbiór Lua 5.5 — nie pełne PUC-Rio.
2. Brak ambient FS / `os.execute` (cel sandboxa).
3. `generate_from_idea` — wektor placeholder (nie pełny PCA).
4. Agenci / hologramy — rejestr sesji hosta, nie pełny runtime paperów HSS.
5. **`top`**, **`nano`** — **DEPRECATED w automatyzacji** (pętla / edytor interaktywny); ręcznie OK.
6. API hosta może dostać pola przed 1.0; surface oznaczony `karmazyn._VERSION`.

## Do 1.0 (po 0.9)

- stabilny kontrakt `karmazyn.*` bez breaking bez major
- opcjonalnie kontrolowany tryb testowy nano/top albo usunięcie z domyślnej listy

## Testy

| Komenda | Co |
|---------|-----|
| `software/test_lua_release.py` | bramka 0.9 (unit + host + kombajn + matrix) |
| `software/lua_bin_matrix.py` | macierz 28 narzędzi |
| `LUA/_run_tests.py` | unit |
| `LUA/kombajn_run.py` | kombajn |

Dokumentacja: [tools_lua.md](../Documents/tools_lua.md) · [START.PL.MD](../Documents/START.PL.MD)
