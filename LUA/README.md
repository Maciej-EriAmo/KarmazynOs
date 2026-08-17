# karmazyn_lua **1.1.2**

Interpreter Lua **5.5 (podzbiór)** na substracie KarmazynOS — **produkcyjny domyślny gość skryptowy**.

| | |
|--|--|
| **Status** | **1.1.2** (production guest) |
| **Sandbox** | **bąbel** — brak ambient FS |
| **Host API** | `karmazyn._VERSION` **1.1.0** (seria 1.x) |
| **Źródło** | monorepo `KarmazynOs/LUA/` |
| **Regresja** | `python release_1_1.py` · `software/test_lua_release.py` |
| **Tools** | pass + skip (`top`, `nano`, `idea` — 16D wycofane) |
| **Kontrakt** | [CONTRACT_1.1.md](CONTRACT_1.1.md) · [RELEASE_1.1.0.md](RELEASE_1.1.0.md) |

## Co znaczy 1.1

**Stabilne w 1.x (breaking → 2.0):**

- montaż gościa: `mount` / `mount_session` / boot `mount_evaluator`
- sandbox: brak `dofile` / ambient FS / `os.execute` / C modules / bytecode
- projekt: searchers preload → memory → project; `strict-project`
- host: global `karmazyn.*` (atomy, step, recall, ui, agents/holograms sesji)
- debug subset + `coroutine.isyieldable` / `close`
- CLI: `run_lua.py` / `python -m karmazyn_lua`
- bramka: unit + kombajn + puc_subset + host smoke + lua_bin matrix

**Celowo poza 1.x:** pełna Lua PUC-Rio, ambient Uniks, C API, pełny PCA hologramów.

## Szybki start

```bash
cd KarmazynOs
python karmazyn_boot.py
python karmazyn_boot.py --project LUA/examples/hello
python software/test_lua_release.py

cd LUA
python run_lua.py run examples/hello
```

```text
karmazyn> :tool ls
karmazyn> return karmazyn._VERSION
```

## Architektura

| Warstwa | Rola |
|---------|------|
| Host | boot / CLI / `EditorBridge` — FS, projekt, lua_bin |
| searchers | [1] preload · [2] memory · [3] project |
| Gość | eval / require / load |
| reach-GC | `register_env_of` / `register_extra_reach` (`name=guest`) |

## Known limits

1. Podzbiór Lua 5.5.
2. Brak ambient FS (cel).
3. `generate_from_idea` — **wycofane** (stary 16D EriAmo). Zwraca nil.
4. Agenci/hologramy — rejestr sesji hosta.
5. `top` / `nano` — nie w automatyce (pętla / edytor).
6. Linie runtime nie zawsze w każdym `error()` (parse mocny).

## Testy

| Komenda | Co |
|---------|-----|
| `LUA/release_1_1.py` | bramka 1.1.0 |
| `software/test_lua_release.py` | bramka monorepo |
| `software/lua_bin_matrix.py` | macierz 28 narzędzi |
| `LUA/_run_tests.py` | unit |
| `LUA/kombajn_run.py` | kombajn |
| `LUA/puc_subset_run.py` | subset testów stylu PUC |

Changelog: [CHANGELOG.md](CHANGELOG.md) · tools: [../Documents/tools_lua.md](../Documents/tools_lua.md)

## 1.1 — bliżej PUC-Rio (bez zmiany fizyki)

Zaimplementowane (patrz [GAP_CLOSE_PLAN.md](GAP_CLOSE_PLAN.md) / [CHANGELOG](CHANGELOG.md)):

- `debug.getinfo|getlocal|setlocal|getupvalue|setupvalue`
- `coroutine.isyieldable` / `close`
- `collectgarbage("step")`; `string.dump` zabronione
- `puc_subset/` + `python puc_subset_run.py`

Nadal poza zakresem: C modules, ambient FS, bytecode, pełny `debug.sethook`.

- [lua_arch_for_programmers.md](../Documents/lua_arch_for_programmers.md)  
- [lua_puc_gap_plan.md](../Documents/lua_puc_gap_plan.md)
