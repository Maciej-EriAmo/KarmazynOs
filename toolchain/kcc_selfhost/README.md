# TB.4 — self-host kcc (w K0)

**Cel:** `kcc` napisany w K0 kompiluje siebie (stage1: host-kcc buduje self-kcc; stage2: self-kcc buduje siebie).

**Status:** **start / Phase 0** — nie „pełny self-host”. Host `kcc` (Rust) nadal jest stage0.

## Fazy

| Faza | Deliverable | Gate |
|------|-------------|------|
| **0** | Szkielet + `tok_kind.k0` (klasyfikacja tokenów jako tablica/reguły w K0) | kcc kompiluje + exit zgodny |
| **1** | Lexer K0: źródło → sekwencja kind+span (bufor fixed arrays) | golden vs host lex na mini fixture |
| **2** | Parser K0: subset AST (fn + let + return + int) | round-trip mini program |
| **3** | Sem + codegen C subset | emit C, gcc link, exit 0 |
| **4** | Zamknięcie: kcc_k0 kompiluje `tok_kind` / siebie w pętli | `verify_selfhost.ps1` |

## Zasady

- Budujemy **od dołu** (lex → parse → emit), nie przepisujemy całego Rusta naraz.
- Język self-host startuje od **podzbioru** K0, który już umie host-kcc.
- Brak stringów w K0 na start → tokeny jako kody `i32`, źródło jako `[i32; N]` (ASCII) lub osobny host helper do wczytania (później).

## Phase 0 (ten katalog)

```text
tok_kind.k0   — kody tokenów + classify_byte(c) → kind
```

```powershell
..\kcc\target\release\kcc.exe tok_kind.k0 --cc -o ..\..\out\kcc\tok_kind
# expect exit 0 after internal asserts (return 0)
```

Dalej: Phase 1 lexer buffer.
