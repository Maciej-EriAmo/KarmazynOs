# TB.4 — self-host kcc (w K0)

**Cel:** `kcc` napisany w K0 kompiluje siebie (stage1: host-kcc buduje self-kcc; stage2: self-kcc buduje siebie).

**Status:** **Phase 1** — lexer buffer w K0. Host `kcc` (Rust) nadal jest stage0.

## Fazy

| Faza | Deliverable | Gate |
|------|-------------|------|
| **0** | `lex_common.k0` + `tok_kind.k0` (classify_byte) | ✅ exit 0 |
| **1** | `lex_buffer.k0` — src ASCII → kind+span (fixed arrays) | ✅ exit 0 + verify_kcc |
| **2** | Parser K0: subset AST (fn + let + return + int) | ❌ |
| **3** | Sem + codegen C subset | ❌ |
| **4** | Zamknięcie: kcc_k0 kompiluje siebie w pętli | ❌ `verify_selfhost.ps1` |

## Zasady

- Budujemy **od dołu** (lex → parse → emit), nie przepisujemy całego Rusta naraz.
- Podzbiór K0, który już umie host-kcc (arrays, structs, for/while, no strings).
- Źródło = `[i32; N]` (ASCII). Tokeny = `kinds` / `starts` / `ends`.

## Kind codes (stable)

| Code | Meaning |
|------|---------|
| 0 | EOF |
| 1 | IDENT |
| 2 | INT |
| 3 | WS (classify only; lexer **skips**) |
| 4 | PUNCT (single byte, Phase 1) |
| 10+ | keywords (later) |

## Pliki

```text
lex_common.k0   — is_ws / is_digit / is_alpha / classify_byte
tok_kind.k0     — Phase 0 smoke (#include common)
lex_buffer.k0   — Phase 1 lex_fill + golden fixtures A–D
```

```powershell
..\kcc\target\release\kcc.exe tok_kind.k0 --cc -o ..\..\out\kcc\tok_kind
..\kcc\target\release\kcc.exe lex_buffer.k0 --cc -o ..\..\out\kcc\lex_buffer
# both expect exit 0
```

Also: `.\toolchain\verify_kcc.ps1` runs both.

## Phase 1 fixtures (lex_buffer)

| Id | Source (ASCII) | Tokens |
|----|----------------|--------|
| A | `a=12+b` | IDENT PUNCT INT PUNCT IDENT EOF |
| B | `x = 7` | IDENT PUNCT INT EOF (WS skipped) |
| C | `//z\nab` | IDENT(ab) EOF (comment skipped) |
| D | `fn` | IDENT EOF (keywords later) |

Dalej: Phase 2 mini-parser on token stream.
