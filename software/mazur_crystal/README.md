# Most Lorentza + Kryształ Mazura (KarmazynOs)

Domyślnie włączany w `karmazyn_boot` po `open_store`:

```
Store (python|native) → LorentzBridge (+ MRC)
```

Wyłączenie: `KARMAZYN_MAZUR=0`.

Pełny opis: [`Documents/MAZUR_CRYSTAL.md`](../../Documents/MAZUR_CRYSTAL.md).

## Co robi most

| API | Znaczenie |
|-----|-----------|
| `tracer` w `metadata` | sonda energii (bez zmiany Atom w Rust) |
| `resonance` / `find_resonating` | \(R = g V^2/(g^2+d_E^2)\) |
| `extra_reach("mazur_crystal_R")` | retencja TOMB gdy \(R\) lub \(\Lambda\) ≥ próg |
| `mrc` | pamięć historyczna \(M\), \(\Lambda=\lambda_R R+\lambda_M M\) |

HRR: `resonance_hrr()` — bez zmian prawa substratu.

## Host / Lua

- `karmazyn.create_atom(id, S, E, T, tracer?)`
- `karmazyn.get_similarity` → Lorentz \(R\)
- `karmazyn.recall` → `resonance_R` (fallback HRR)
- `karmazyn.set_context` / `get_tracer` / `set_tracer`
- `:tool ping` / `recall` / `touch` / `ls` — logiczne id na native

## Test (PowerShell)

```powershell
cd C:\Users\drwis\KarmazynOs
$env:PYTHONPATH = "archiwum\kernel_python;software;native;."
$env:KARMAZYN_SUBSTRATE = "python"
$env:KARMAZYN_MAZUR = "1"
python -m mazur_crystal.test_bridge
```
