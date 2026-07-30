# Changelog — karmazyn_lua

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
