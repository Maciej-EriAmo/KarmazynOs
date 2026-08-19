
# SESSION_PROGRESS — kcc / Tor B (wlasny kompilator)

**Data:** 2026-08-07  
**Repo:** KarmazynOs `main` (kcc **0.6.2** / TB.3d+ + TB.4 **Phase 4** self-host loop)

## Polityka
- Kompilator = **wlasny** (`kcc`, jezyk K0 → C99)
- Edytor / OS / stage0 `rustc` (tylko build kcc) / `gcc` (link) = obce OK
- TB.4: start od Phase 0 w `toolchain/kcc_selfhost/` — nie pelny self-host

## Stan kcc 0.6.1
| Element | Stan |
|---------|------|
| structs define + field + nested chain | OK |
| return-struct by value | OK |
| for / break / continue | OK |
| type-unify + return-path | OK |
| TB.4 Phase 0 `tok_kind.k0` | OK |
| TB.4 Phase 1 `lex_buffer.k0` | OK (kind+span fixtures A–D) |
| TB.4 Phase 2 `parse_mini.k0` | OK |
| TB.4 Phase 3 `emit_mini.k0` | OK (IR + sem + emit C + eval) |
| TB.4 Phase 4 `selfhost_dump` | OK — dump C → gcc → 42/1/3/15 |

## Critical K0
- thermal / tick / atom_table / store_mini
- `struct_point.k0` (exit 50)
- `kcc_selfhost/`: tok_kind + lex_buffer + parse_mini + emit_mini + **selfhost_dump** (P4)

## Gate
```
.\toolchain\verify_kcc.ps1
# → KCC_VERIFY_OK  (zawiera P4)
.\toolchain\verify_selfhost.ps1
# → KCC_SELFHOST_OK
```

## Nastepne (priorytet projektu)
1. **P4 stoi** — podzbiór, nie pełny self-host kcc  
2. Tor A / product (gdy praca)  
3. TB.5 (backend bez gcc) — tylko świadomie
