# Kontrakt skryptów — karmazyn_lua **1.1.1**

Dla autorów narzędzi `lua_bin`, projektów gościa i agentów.

**1.1.1:** locale w blokach `do`/`for`/… przeżywają `collectgarbage`; `eval_line` **nie** zostawia `local` na `_G` między liniami (użyj globali albo jednej linii / `run_source`).

## Co jest gwarantowane (1.x)

| Obszar | Gwarancja |
|--------|-----------|
| Język | Podzbiór Lua **5.5**: tabele, funkcje, metametody, goto, vararg, integer/float, bitops |
| Stdlib | `math`, `string` (w tym pack), `table`, `utf8`, `os` (wirtualny), `coroutine`, `debug` (subset) |
| Sandbox | **Brak** ambient FS, `dofile`, `os.execute`, C modules, bytecode |
| Montaż | `mount` / sesja / project searchers (preload → memory → project host) |
| Host | Global `karmazyn.*` (atomy, step, recall, ui, …) gdy boot wstrzyknie hosta |
| GC | `collectgarbage` → settle + weak/`__gc` **na** fizyce T×reach |
| Wersja | `karmazyn_lua.__version__` = **1.1.0**; gość: `_VERSION` = `"Lua 5.5"` |

## debug.* (1.1)

**Jest:** `traceback`, `getinfo`, `getlocal`, `setlocal`, `getupvalue`, `setupvalue`  
**Nie ma:** `sethook`, `getregistry`, `debug`, uservalue — i nie będzie w 1.x jako backdoor do jądra.

Upvalues = wiązania bąbla `fn.env` (model Karmazyn), nie 1:1 sloty PUC-Rio.

## Host `karmazyn.*`

- T atomów: skala jądra **0..T_MAX** (zwykle 100); używaj `karmazyn.T_INIT` / `T_HOT` / …
- `list_atoms` = surface Φ (`create_atom`), nie heap Lua (`a0`, `a1`, …)
- Trwałość: `consolidate` / root — nie pliki OS z gościa

## Czego nie pisać w skryptach gościa

```lua
-- NIE (celowo)
io.open("/etc/passwd")
os.execute("rm -rf /")
dofile("x.lua")
require("socket.core")   -- C module
string.dump(function() end)
load(bin, name, "b")
```

```lua
-- TAK
local m = require("mymod")          -- preload / project host
print(karmazyn.list_atoms())        -- gdy host zamontowany
local f, err = load("return 1+1")   -- tylko tekst
```

## Błędy

- `pcall` / `xpcall`: obiekt błędu = czysta wartość (`error("x")` → `"x"`)
- nieprzechwycony: traceback z **chunk:line** gdy parser oznaczył linie
- budget sesji: `session budget exceeded` przy limicie hosta

## Breaking

- Seria **1.x**: kontrakt sandbox + surface hosta stabilne  
- **2.0**: dopiero breaking (np. zmiana API hosta / semantyki global)

## Testy / bramka

```bash
python release_1_1.py
python kombajn_run.py
python puc_subset_run.py
```
