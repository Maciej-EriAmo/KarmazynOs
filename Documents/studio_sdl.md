# KarmazynOs Studio (SDL2) — Stage 2 viewer

**Status:** living  
**Stack:** Stage 1 matryca T + pygame (SDL2 via pygame) + shell

## Zasada (Luneta)

| Warstwa | Odpowiedzialność |
|---------|------------------|
| Store / thermal | heat, tick, project_hot |
| `karmazyn_io_sdl` | okno, klawiatura, mysz, blit |
| shell | `feed` linii |

Silnik **nie** importuje pygame w `kernel/`.

## Start

```bash
python software/karmazyn_studio.py
python software/karmazyn_studio.py --python
python start.py --studio
python software/karmazyn_boot.py --studio

# smoke bez okna
python software/karmazyn_studio.py --check --python
```

Wymaga: `pip install pygame` (SDL2 wbudowane w pygame-ce).

## Layout

| Warstwa | Co |
|---------|-----|
| **Tło (całe okno)** | mapa termiczna — siatka komórek kolor = T (`project_hot`) |
| **Pierwszy plan** | **prompt na całe okno** — log shell + `karmazyn>` |
| Status | cienki pasek na dole |

## Sterowanie

| Klawisz / akcja | Efekt |
|-----------------|--------|
| wpisywanie + Enter | `KeyboardAdapter` + `shell.feed` |
| hover na komórce tła | `heat_hit` |
| klik komórki | `set_focus` |
| scroll | historia logu |
| F5 | `settle(10)` |
| Esc | wyjście |

## Anti self-heat

Paint tła: `project_hot(mark_visible=False)`.  
`note_visible(io:display)` tylko co `tick_every` klatek (nie 30×/s).

## Pliki

- `software/karmazyn_io_sdl.py` — SdlIo, KarmazynStudio  
- `software/karmazyn_studio.py` — CLI  
- `software/test_studio_sdl.py` — smoke `--check`
