# karmazyn_lua **1.0.0**

Interpreter Lua **5.5 (podzbiór)** na substracie KarmazynOS — **stabilny domyślny gość skryptowy**.

| | |
|--|--|
| **Status** | **1.0.0** (stable) |
| **Sandbox** | **bąbel** — brak ambient FS |
| **Host API** | `karmazyn._VERSION` **1.0.0** (frozen na 1.x) |
| **Źródło** | monorepo `KarmazynOs/LUA/` |
| **Regresja** | `python software/test_lua_release.py` |
| **Tools** | 26 pass / 2 skip (`top`, `nano` — ręcznie) |

## Co znaczy 1.0

**Stabilne w 1.x (breaking → 2.0):**

- montaż gościa: `mount` / `mount_session` / boot `mount_evaluator`
- sandbox: brak `dofile` / ambient FS / `os.execute`
- projekt: searchers preload → memory → project; `strict-project`
- host: global `karmazyn.*` (atomy, step, recall, ui, agents/holograms sesji)
- CLI: `run_lua.py` / `python -m karmazyn_lua`
- bramka: unit + host smoke + kombajn + lua_bin matrix

**Celowo poza 1.0:** pełna Lua 5.5 PUC-Rio, ambient Uniks, pełny PCA hologramów.

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
3. `generate_from_idea` — placeholder wektor.
4. Agenci/hologramy — rejestr sesji hosta.
5. `top` / `nano` — nie w automatyce (pętla / edytor).
6. Linie runtime nie zawsze w każdym `error()` (parse mocny).

## Testy

| Komenda | Co |
|---------|-----|
| `software/test_lua_release.py` | bramka 1.0 |
| `software/lua_bin_matrix.py` | macierz 28 narzędzi |
| `LUA/_run_tests.py` | unit |
| `LUA/kombajn_run.py` | kombajn |

Changelog: [CHANGELOG.md](CHANGELOG.md) · tools: [../Documents/tools_lua.md](../Documents/tools_lua.md)

## Dalsza ewolucja (1.1) — bliżej PUC-Rio bez zmiany fizyki

- [lua_arch_for_programmers.md](../Documents/lua_arch_for_programmers.md) — różnice architektoniczne dla programistów  
- [lua_puc_gap_plan.md](../Documents/lua_puc_gap_plan.md) — plan: debug, integer/float, weak/__gc, string, coroutine, puc-subset
