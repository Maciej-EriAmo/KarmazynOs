# Most Lorentza + Kryształ Mazura (KarmazynOs)

**Status:** wdrożone w bootcie produkcyjnym (native + Python).  
**Kod:** `software/mazur_crystal/` · szew: `karmazyn_boot.py` po `open_store`.

## Po co

Oddzielenie **treści** (`E` / HRR) od **sondy energetycznej** (`tracer`) oraz **bieżącego rezonansu \(R\)** od **pamięci historycznej \(M\)** (MRC).

Źródło metodologii: badania w `Kernel Karmazyn/experiments/mazur_crystal/` + `Krysztal.txt` · empiria: Bridge Transformer (Lorentz).

## Pipeline

```text
tracer → R (Lorentz) → retencja GC (extra_reach) → MRC (M, Λ) → HSL wybór peera (DBase)
```

\(R = g\cdot V^2 / (g^2 + d_E^2)\) — \(V\) domyślnie Jaccard po `E` (HRR opcjonalnie `use_hrr=True`).

\(\Lambda = \lambda_R\cdot R + \lambda_M\cdot M\) — retencja TOMB gdy \(\Lambda \ge R_{retain}\).

## Boot

Domyślnie **włączony**. Wyłączenie:

```text
set KARMAZYN_MAZUR=0
```

Log startu: `most Lorentza — R+retencja+MRC`.

## Host / Lua

| API | Znaczenie |
|-----|-----------|
| `create_atom(id, S, E, T, tracer?)` | opcjonalna energia sondy |
| `get_similarity(a,b)` | \(R\) Lorentza |
| `recall(q, k)` | `resonance_R` (fallback HRR) |
| `set_context` / `get_tracer` / `set_tracer` | sonda systemu / odczyt |

Narzędzia: `:tool ping`, `:tool recall`, `:tool touch`, `:tool ls` — logiczne id na native (nie u32).

## Test

```powershell
$env:PYTHONPATH = "archiwum\kernel_python;software;native;."
python -m mazur_crystal.test_bridge
```

## Powiązania

- DBase: ten sam pakiet `mazur_crystal/`, ranking peerów w `karmazyn_hsl.py`
- Docs sieci: DBase `docs/SESSION_L0_KPC.md` (Faza 6)
- `tools_lua.md` — surface hosta
