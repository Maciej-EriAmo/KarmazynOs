# KarmazynOS — Quick Start

| Component | Version |
|-----------|---------|
| Kernel | **1.1.0** |
| Lua guest | **`karmazyn_lua 0.9.0`** |
| Host API | **`karmazyn._VERSION` 1.0.0** |

PL start: **[START.PL.MD](START.PL.MD)** · tools: **[tools_lua.md](tools_lua.md)** · matrix: **[lua_bin_status.md](lua_bin_status.md)**

```bash
git clone https://github.com/Maciej-EriAmo/KarmazynOs
cd KarmazynOs
python karmazyn_boot.py
python karmazyn_boot.py --project LUA/examples/hello
python software/test_lua_release.py   # RELEASE GATE OK  0.9.0
```

```text
karmazyn> :tool ls
karmazyn> return x * 2
```

Guest sandbox = bubble. Tool smoke: **26 pass / 2 skip** (`top`, `nano` — manual only).

Canonical Lua tree: monorepo `LUA/`.
