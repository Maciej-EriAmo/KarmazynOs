# TB.4 — self-host kcc (w K0)

**Cel:** `kcc` napisany w K0 kompiluje siebie.

**Status:** **Phase 3** — IR + sem + emit C (ASCII buffer) + eval. Host `kcc` = stage0.

## Fazy

| Faza | Deliverable | Gate |
|------|-------------|------|
| **0** | `lex_common` / `tok_kind` | ✅ |
| **1** | `lex_engine` / `lex_buffer` | ✅ |
| **2** | `parse_mini` | ✅ |
| **3** | `emit_mini` — IR, sem, emit C, eval | ✅ |
| **4** | Self-host loop (kcc_k0 → C → compile) | ❌ |

## Pipeline Phase 3

```text
ASCII src → lex_fill → IR (RPN stmts) → sem_check → eval_program
                                              ↘ emit_program → C as [i32] bytes
```

### IR ops
| Op | Meaning |
|----|---------|
| 1 | INT value |
| 2 | IDENT span |
| 3/4 | ADD / SUB |
| 5 | LET name + expr…END |
| 6 | RET expr…END |
| 7 | FN |
| 8 | END |

### Emit shape
```c
int main(void){
  int32_t x = …;
  return …;
}
```
(without real `stdio` — buffer only; host does not yet write `.c` file from K0)

## Pliki

```text
lex_common.k0  lex_engine.k0
tok_kind.k0    lex_buffer.k0
parse_mini.k0  emit_mini.k0
```

```powershell
..\kcc\target\release\kcc.exe emit_mini.k0 --cc -o ..\..\out\kcc\emit_mini
.\toolchain\verify_kcc.ps1
```

## Phase 3 fixtures (emit_mini)

| Id | Case | Expect |
|----|------|--------|
| A | `return 42` | eval=42; C has `int main` + `return` + `42` |
| B | `let x=1; return x` | eval=1; emit `int32_t` |
| C | `return 1+2` | eval=3; emit `+` |
| D | `return y` undeclared | **sem reject** |
| E | `let a=10; let b=a+5; return b` | eval=15 |

## Dalej (Phase 4)

- Zapis bufora C na dysk (host helper lub rozszerzenie K0)
- `kcc` w K0 kompiluje `tok_kind` / `emit_mini` przez host-kcc bootstrap
- `verify_selfhost.ps1`
