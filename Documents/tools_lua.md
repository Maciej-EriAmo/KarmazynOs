# Jak pisać narzędzie Lua na KarmazynOS

**karmazyn_lua 1.0.0** · host API `karmazyn._VERSION` = **1.0.0** (frozen on 1.x)

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
| `create_atom(id, S, E, T [, tracer])` | tworzy atom; `tracer` = energia sondy (Lorentz) |
| `delete_atom(id)` | usuwa |
| `clone_atom(src, dst)` | kopia |
| `consolidate(id)` | bąbel trwały (root) |
| `step(n)` / `get_epoch()` | ticki / epoki sesji |
| `get_temperature()` | proxy „ciepła” systemu |
| `get_resources()` | `store.stats()` (+ flagi `lorentz_bridge` / `mrc` gdy most) |
| `recall(query, k)` | rezonans **Lorentza \(R\)** (fallback HRR / substring) |
| `get_similarity(id1, id2)` | \(R\) Lorentza (treść + tracer) |
| `set_context(id)` | atom-sonda systemu (retencja GC / MRC) |
| `get_tracer(id)` / `set_tracer(id, energy)` | odczyt / zapis sondy |

Most Lorentza: [MAZUR_CRYSTAL.md](MAZUR_CRYSTAL.md) · `KARMAZYN_MAZUR=0` wyłącza.
| `list_bubbles()` | bąble z etykietą + `content` |
| `list_agents()` / `spawn_agent` / `delete_agent` | rejestr **sesji** (nie Store, nie procesy OS) |
| `list_holograms()` / `create_hologram` | etykiety **sesji** (nie HRR) |
| `generate_from_idea` | **wycofane** — zawsze nil (stary 16D EriAmo) |
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

**Macierz live:** [lua_bin_status.md](lua_bin_status.md) · `python software/lua_bin_matrix.py`

| Wynik | Narzędzia |
|-------|-----------|
| **pass** | ls, cat, touch, rm, cp, mv, df, free, du, find, grep, stat, step, whoami, uptime, clear, man, ps, kill, lsh, lsb, kedit, consolidate, ping, recall |
| **skip** | `top`, `nano` (pętla/edytor); `idea` (wycofane 16D); starlink* (osobny seed) |

`generate_from_idea` = wycofane. `ps`/`lsh` = sesja, nie jądro.
