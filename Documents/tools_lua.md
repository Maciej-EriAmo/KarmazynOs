# Jak pisać narzędzie Lua na KarmazynOS

**Sandbox = bąbel.** Skrypt nie widzi dysku hosta. Widzi **global `karmazyn`**
wstrzyknięty przez hosta przy starcie bootu.

## Uruchomienie

```bash
# lista narzędzi
python karmazyn_boot.py
karmazyn> :tool

# konkretne narzędzie (lua_bin/<name>.lua)
karmazyn> :tool ls
karmazyn> :tool whoami
```

Ścieżka: `KARMAZYN_LUA_BIN` lub monorepo `lua_bin/`.

## Minimalny skrypt

```lua
-- lua_bin/hello_tool.lua
local atoms = karmazyn.list_atoms()
print("atomów: " .. #atoms)
```

```text
karmazyn> :tool hello_tool
```

## API hosta (`karmazyn.*`) — surface v1

| Funkcja | Opis |
|---------|------|
| `read_line(prompt)` | wczytaj linię (REPL / kolejka testowa) |
| `list_atoms([state])` | tablica proxy atomów (`HOT`/`WARM`/…) |
| `get_atom(id)` | proxy lub nil |
| `create_atom(id, S, E, T)` | tworzy atom |
| `delete_atom(id)` | usuwa |
| `clone_atom(src, dst)` | kopia |
| `consolidate(id)` | bąbel trwały (root) |
| `step(n)` / `get_epoch()` | ticki / epoki sesji |
| `get_temperature()` | proxy „ciepła” systemu |
| `get_resources()` | `store.stats()` |
| `recall(query, k)` | resonance HRR + fallback tekstowy |
| `get_similarity(id1, id2)` | podobieństwo |
| `list_bubbles()` | bąble z etykietą + `content` |
| `list_agents()` / `spawn_agent(name, task, prisms)` / `delete_agent(pid)` | agenci sesji |
| `list_holograms()` / `create_hologram(id, topic, atom_ids)` | idee w sesji |
| `generate_from_idea(id, prompt, temp)` | wektor syntetyczny (placeholder) |
| `clear_screen()` / `sleep(sec)` | UI terminala |
| `ui.progress_bar(v, max, width)` | pasek tekstowy |
| `ui.draw_frame(title, lines)` | ramka tekstowa |
| `fs.read/write`, `cache.read/write` | mini VFS w pamięci sesji |

### Proxy atomu

```lua
local a = karmazyn.get_atom("x")
print(a.id, a.S, a.E, a.state, a.get_T())
a.set_E("nowe")
a.refresh()
a.set_state("HOT")   -- HOT|WARM|COLD|TOMB
a.consolidate()
```

## Zasady

1. **Nie zakładaj** `dofile` / `io.open` / `os.execute` — ich nie ma.
2. I/O użytkownika → `karmazyn.read_line` (host może wstrzyknąć kolejkę).
3. Trwałość między restartami → `consolidate` / bąble-korzenie, nie pliki OS.
4. Narzędzie = plik `lua_bin/name.lua` uruchamiany przez `:tool name` (chunk, niekoniecznie `return M`).

## Testy smoke

```bash
cd software
python test_host_tools.py -v
```

## Status

**Macierz live:** [lua_bin_status.md](lua_bin_status.md) · generator: `python software/lua_bin_matrix.py`

| Wynik | Narzędzia |
|-------|-----------|
| **pass (26)** | ls, cat, touch, rm, cp, mv, df, free, du, find, grep, stat, step, whoami, uptime, clear, man, ps, kill, lsh, lsb, idea, kedit, consolidate, ping, recall |
| **skip (2)** | `top` (nieskończona pętla), `nano` (edytor interaktywny) |

`generate_from_idea` = wektor placeholder (nie pełny PCA).
