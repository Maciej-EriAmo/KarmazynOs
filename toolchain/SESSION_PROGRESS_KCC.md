
# SESSION_PROGRESS — kcc / Tor B (wlasny kompilator)

**Data:** 2026-08-07  
**Repo:** KarmazynOs `main` (kcc **0.6** / TB.3d structs + TB.3c for/break + TB.2f/TB.3b golden)

## Polityka
- Kompilator = **wlasny** (`kcc`, jezyk K0 → C99)
- Edytor / OS / stage0 `rustc` (tylko build kcc) / `gcc` (link) = obce OK
- NIE: self-host kcc (TB.4), NIE: full rustc

## Stan kcc 0.6
| Element | Stan |
|---------|------|
| lex / parse / codegen | OK |
| `#include "x.k0"` | OK |
| fixed arrays + index + array params | OK |
| `for` / `break` / `continue` | OK (0.5 / TB.3c) |
| **structs** define + `p.f` + `p.f = e` + by-value params | OK (0.6 / TB.3d) |
| `sem` undeclared / arity / `%` f64 / redef / fields | OK |
| `--safe` bounds → `abort()` | OK |
| **type-unify** let/assign/index/call/return | OK (0.4) |
| **return-path** all branches return | OK (0.4) |
| golden reach store_mini↔slab | OK (TB.3b) |

## Critical K0 (kompilowane tylko kcc)
- `thermal_lib.k0` / `thermal.k0` / `tick_skeleton.k0`
- `atom_table.k0` / `store_mini.k0`
- `for_break.k0` / **`struct_point.k0`** (exit 32)

## Gate
```
.\toolchain\verify_kcc.ps1
# → KCC_VERIFY_OK
```

## Docs
- `Documents/TOR_B_TOOLCHAIN.pl.md`
- `Documents/BOOTSTRAP_STAGES.pl.md` (Tor A vs B)
- `toolchain/kcc/README.md`

## Nastepne
1. TB.4 self-host (daleko)  
2. TB.5 own backend bez gcc (daleko)  
3. Optional: return-struct / nested field polish

## Holon
Fact + close w Karmin_Ae (projekt Karmazyn).
