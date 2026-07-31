# I/O × matryca T — Stage 1 (Gentoo-style)

**Status:** domknięte (2026-07-31)  
**Wzór:** Gentoo Stage 1 — minimalny, poprawny bootstrap; brak cichej degradacji.

## Zasady Stage 1

1. **Działa na python i native** — jedna tabela `name → aid` (str lub int).
2. **FAIL, nie WARN** — `attach_thermal` rzuca `ThermalMountError`; boot → `BootError`, chyba że `KARMAZYN_IO_OPTIONAL=1` (rescue).
3. **Puste wejście ≠ heat** — anti self-heat na EOF/kolejce.
4. **`project_hot` nie grzeje skanu** — `mark_visible=False` domyślnie; `frame()` grzeje tylko `io:display`.
5. **Write/log nie grzeje** — widoczność tylko przez jawne `note_visible`.

## Artefakty

| Plik | Rola |
|------|------|
| `software/karmazyn_io.py` | IoPort + ThermalSurface stage=1 |
| `software/karmazyn_boot.py` | montaż + twarde FAIL |
| `software/test_io_thermal.py` | python + native gates |
| `software/sim_io_thermal.py` | symulacja ręczna |

## Env

| Zmienna | Znaczenie |
|---------|-----------|
| `KARMAZYN_IO` | `stdio` \| `queue` \| `null` |
| `KARMAZYN_IO_OPTIONAL=1` | rescue: brak matrycy = WARN, nie FAIL |

## Gate

```bash
python -m unittest software.test_io_thermal software.test_host_tools -v
# native boot musi mieć thermal stage=1
```

## Poza Stage 1 (świadomie)

- SerialIo, VESA blit, scancode map  
- BootConfig/cmdline parser  
- budżet ciepła per-tick  
- ekspozycja matrycy w Lua host API  

→ Stage 2+.
