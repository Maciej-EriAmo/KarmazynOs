# Changelog — karmazyn_lua

## 1.1.2 — 2026-07-31

**Quality pass (P1 z recenzji 1.1.1).**

- `collectgarbage("count")` = atomy w grafie gościa (G + live envs), nie cały heap Store.
- `__gc`: błędy finalizera logowane do `_out` (`[__gc error] …`), nie połykane w ciszy.
- `_bubble_reachable`: korzenie = G + store.roots + `_active_envs`.
- `debug.getupvalue`: pomija `_ENV` (mniej mylące).
- **puc_subset** 5 → **13** plików (multi, meta, pcall, bit, goto, load, weak, nested_gc).
- matrix `idea`: nota STUB placeholder.

## 1.1.1 — 2026-07-31

**Hotfix production (P0 z surowej recenzji).**

- **P0-1:** `extra_reach` obejmuje bloki `do`/`if`/`while`/`repeat`/`for`/`for-in` — locale nie giną po `collectgarbage`.
- **P0-2:** `eval_line` na izolowanym scope (`_ENV=G`), nie brudzi `G` localami między liniami.
- Testy: `test_nested_block_locals_survive_gc`, `test_eval_line_does_not_pollute_G`.

## 1.1.0 — 2026-07-31

**Production guest release.**

- **debug.*** subset: `getinfo`, `getlocal`, `setlocal`, `getupvalue`, `setupvalue` (+ `traceback`); bez `sethook`/`getregistry`.
- **coroutine.isyieldable**, **coroutine.close** (5.4).
- **collectgarbage("step")**; `string.dump` **zabronione** (sandbox).
- Runtime `error`/`assert`: **chunk:line** w tracebacku; `pcall` nadal czysty msg.
- Ramki `_call_stack` jako rekordy (traceback + debug).
- Testy golden **weak** / **`__gc`**.
- **puc_subset/** + `puc_subset_run.py`.
- Bramka **`release_1_1.py`**; monorepo `test_lua_release` akceptuje 1.1.x.
- Dokumenty: [CONTRACT_1.1.md](CONTRACT_1.1.md), [RELEASE_1.1.0.md](RELEASE_1.1.0.md).
- Host surface `karmazyn._VERSION` = **1.1.0**.

## 1.0.0 — 2026-07-29

- **Stable 1.0.0** — domyślny gość skryptowy KarmazynOS.
- Host API `karmazyn._VERSION` = **1.0.0** (frozen na serii 1.x).
- `attach_lua_bin`: bez nadpisywania `ev.project` (preload gdy brak projektu).
- Reach hooks + portable kernel paths (z 0.9.1).
- Macierz tools 26/28; gate: unit + host + kombajn + matrix.

## 0.9.1 — 2026-07-29

- Fix reach: `register_env_of` / `register_extra_reach` (`name=guest`).
- Portable kernel discovery (`_paths.py`).
- Host `_VERSION` aligned to 0.9.0.

## 0.9.0 — 2026-07-29

- Release 0.9: project host, CLI, boot tools, matrix 26/28.

## 0.8.0-alpha — 2026-07-29

- Pierwsza formalna alpha.
