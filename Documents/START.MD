# KarmazynOS — Quick Start

| Component | Version |
|-----------|---------|
| Kernel | **1.1.0** |
| Substrate | **Rust native `0.1.0`** (default) · Python = reference |
| Lua guest | **`karmazyn_lua 1.0.0`** (stable) |
| Host API | **`karmazyn._VERSION` 1.0.0** |
| Boot | v0.5+ |

PL: **[START.PL.MD](START.PL.MD)** · [tools_lua.md](tools_lua.md) · [lua_bin_status.md](lua_bin_status.md)

```bash
cd KarmazynOs
python karmazyn_boot.py
python karmazyn_boot.py --project LUA/examples/hello
python software/test_lua_release.py   # RELEASE GATE OK  1.0.0
```

```text
karmazyn> :tool ls
karmazyn> return karmazyn._VERSION
```

Guest sandbox = bubble. Tool matrix: **26 pass / 2 skip** (`top`, `nano`).  
Canonical tree: monorepo `LUA/`.
