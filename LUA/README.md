# karmazyn_lua — gość Lua 5.5 (podzbiór) na KarmazynOS

Interpreter Lua osadzony na substracie Karmazyn: **tabela = Bubble**, reach-GC,  
kontrakt gościa (A–H). **Sandbox = bąbel** — bez ambient FS w gościu.

## Szybki start

```bash
# z katalogu LUA/ (wymaga jądra: Kernel Karmazyn lub monorepo)
python run_lua.py run examples/hello
python run_lua.py check examples/hello
python run_lua.py path lib.greeter -p examples/hello
python run_lua.py repl examples/hello

python _run_tests.py      # testy unit
python kombajn_run.py     # kombajn integracyjny
```

Z bootu OS (katalog monorepo):

```bash
python karmazyn_boot.py --project LUA/examples/hello
# :project | :check | :run | :reload util
```

## Architektura host → bąbel

| Warstwa | Rola |
|---------|------|
| Host (CLI / boot / `EditorBridge`) | czyta dysk, montuje projekt |
| `package.searchers[1]` preload | `tools/` / `lua_bin` |
| `package.searchers[2]` memory | bufory edytora (`put_buffer`) |
| `package.searchers[3]` project | pliki pod rootem projektu |
| Gość Lua | `require` / `load` / eval — bez `dofile` |

## API publiczne (Python)

```python
from karmazyn_kernel import Store
from karmazyn_lua import mount, mount_session, GuestSession, EditorBridge

ev = mount_session(Store(thermal=True), project="examples/hello")
# lub
sess = GuestSession(project="examples/hello")
kind, text = sess.run()
```

## Flagi CLI

| Flaga | Znaczenie |
|-------|-----------|
| `--project` / `-p` | root projektu |
| `--tools` | katalog preload |
| `--lua-bin` | tools + module root |
| `--strict-project` / `--no-strict-project` | run tylko pod rootem |
| `--caps` | `default` \| `strict` \| `compute` \| `full` |

## Pliki kluczowe

| Plik | Rola |
|------|------|
| `evaluator.py` | ewaluator, builtins, `run_source` |
| `project.py` / `session.py` | projekt, searchery, sesja |
| `cli.py` / `run_lua.py` | CLI hosta |
| `editor_bridge.py` | most edytora |
| `karmazyn_lua_*.py` | biblioteki std (bloki) |

## Status

- Język + metatabele + liby + GC: **v1**
- Multi-file / CLI / boot / memory / strict-project: **v1**
- Pełne host bindings `karmazyn.*` dla `lua_bin`: **kolejna faza**

Zasada Karmazynu: **bezpieczeństwo na granicy bąbla**, nie w magii ścieżek OS.
