# Plan: Starlink na atomach (checklista)

**Status:** MVP **zamknięty** (fazy 0–3 + HTML).  
**Dokument kanoniczny (EN — cel, dowód, quick start):** [STARLINK_ATOMS.md](STARLINK_ATOMS.md)

---

## Model (skrót)

```text
Bubble root: starlink
  ├─ sats   → starlink:sat
  ├─ grid   → starlink:cell   (T = gęstość / heatmapa)
  └─ shell:N → grupa inklinacji
```

Prawo: **T = kiedy**, **reach = czy**. Multi-task na jednym Store; Lua na **izolowanym** Store widoku.

---

## Fazy

| Faza | Status |
|------|--------|
| 0 Spike | ✅ |
| 1 SGP4 + live | ✅ |
| 2 hot-only | ✅ |
| 3 Lua isolate + tools | ✅ |
| HTML report | ✅ |

---

## Pliki

| Ścieżka | Rola |
|---------|------|
| `software/starlink_atoms.py` | host CLI |
| `lua_bin/starlink.lua` / `starlink_hot.lua` | tools |
| `Documents/STARLINK_ATOMS.md` | EN overview + proof |
| `out/` | tylko generowane (gitignore) |

---

## Komendy

```powershell
cd C:\Users\drwis\KarmazynOs
python software/starlink_atoms.py --limit 0 --prop sgp4 --hot-only --html --open-html
python software/starlink_atoms.py --limit 400 --lua
python software/starlink_atoms.py --offline-demo --limit 40 --full-grid
```

---

## Next (opcjonalne)

- seed w boot (`:tool starlink` na żywym katalogu)
- Studio/SDL blit, `note_visible`
- KarminQL / KAFD / gossip
- test smoke w `software/`

---

*Szczegóły i metryki skuteczności → STARLINK_ATOMS.md (EN).*
