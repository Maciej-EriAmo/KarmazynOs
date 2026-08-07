# TB.4 — self-host kcc (w K0)

**Cel:** `kcc` napisany w K0 kompiluje siebie (stage1: host-kcc buduje self-kcc; stage2: self-kcc buduje siebie).

**Status:** **Phase 2** — mini-parser na token stream. Host `kcc` (Rust) nadal jest stage0.

## Fazy

| Faza | Deliverable | Gate |
|------|-------------|------|
| **0** | `lex_common.k0` + `tok_kind.k0` | ✅ |
| **1** | `lex_engine.k0` + `lex_buffer.k0` (kind+span) | ✅ |
| **2** | `parse_mini.k0` — fn / let / return / int expr | ✅ |
| **3** | Sem + codegen C subset | ❌ |
| **4** | Self-host loop | ❌ |

## Zasady

- Od dołu: lex → parse → emit.
- Źródło = `[i32; N]` ASCII; tokeny = kinds/starts/ends.
- Keyword match = porównanie spanu z literami (`fn`/`let`/`return`/`i32`), nie stringi K0.

## Kind codes

| Code | Meaning |
|------|---------|
| 0 | EOF |
| 1 | IDENT |
| 2 | INT |
| 3 | WS (skip) |
| 4 | PUNCT |

## Pliki

```text
lex_common.k0   — classify helpers
lex_engine.k0   — lex_fill + kw_* + int_value
tok_kind.k0     — Phase 0 smoke
lex_buffer.k0   — Phase 1 golden A–D
parse_mini.k0   — Phase 2 parser + golden A–F
```

```powershell
..\kcc\target\release\kcc.exe parse_mini.k0 --cc -o ..\..\out\kcc\parse_mini
# expect exit 0
.\toolchain\verify_kcc.ps1
```

## Phase 2 grammar

```text
program  := fn_def+
fn_def   := 'fn' IDENT '(' ')' [ '->' 'i32' ] '{' stmt* '}'
stmt     := 'let' IDENT '=' expr ';' | 'return' expr ';'
expr     := primary ( ('+'|'-') primary )*
primary  := INT | IDENT
```

`->` = two PUNCTs (`-` `>`), not one token.

## Phase 2 fixtures (parse_mini)

| Id | Source | Expect |
|----|--------|--------|
| A | `fn main(){return 42;}` | 1 fn, 1 ret, last_int=42 |
| B | `fn main(){let x=1;return x;}` | 1 let, 1 ret |
| C | `fn f()->i32{return 0;}` | arrow + i32 |
| D | `fn main(){return 1+2;}` | 2 int lits |
| E | `fn main(){return;}` | **reject** |
| F | `main(){return 1;}` | **reject** (no `fn`) |

Dalej: Phase 3 — sem + emit C subset z tego AST (stats → proste C lub flat node table).
