# Changelog — karmazyn_lua

## 0.9.1 — 2026-07-29

- **Fix reach hooks:** `register_env_of` / `register_extra_reach` with `name="guest"` (no stacking on remount / `:guest`).
- **Portable kernel discovery:** `LUA/_paths.py` — monorepo `kernel/` first; removed developer absolute paths from CLI/tests.
- **Host API version:** `karmazyn._VERSION` = `0.9.0` (aligned with package line; freeze at 1.0).
- Tests: `test_reach_hooks_registered_not_stacked`.

## 0.9.0 — 2026-07-29

- **Release 0.9.0** — domyślny gość skryptowy KarmazynOS.
- Macierz `lua_bin`: **26 pass / 2 skip** (`top`, `nano` DEPRECATED w automatyce).
- Host API `karmazyn._VERSION` = **1.0.0**.
- Bramka: unit + host smoke + kombajn + matrix (`test_lua_release.py`).
- Dokumentacja START / tools / known limits zaktualizowana pod 0.9.

## 0.8.0-alpha — 2026-07-29

- Pierwsza formalna alpha: projekt multi-file, CLI, boot `:project`/`:run`/`:tool`.
- Host bindings `karmazyn.*`, smoke tools, tag `lua-v0.8.0-alpha`.
