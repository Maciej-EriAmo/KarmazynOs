# Tor B — łańcuch narzędzi (Gentoo / LFS pattern)

**Status:** seed · **Data:** 2026-08-06  
**Nie mylić z:** Torem A (`BOOTSTRAP_STAGES.pl.md` — runtime bez Pythona na **host** `rustc`).

## Wzorzec

Jak **Gentoo stage\*** i **Linux From Scratch**:

> **Własne narzędzia** kompilują **ważne biblioteki**, aż world nie zależy od obcego host-kompilatora.

| Faza LFS/Gentoo | U nas (cel) |
|-----------------|-------------|
| stage0 / host seed | zewnętrzny `rustc`+Cargo (mamy) |
| tymczasowy toolchain | **brak** — tu zaczyna się prawdziwa praca Tora B |
| rebuild lib własnymi toolami | `karmazyn_slab`, `karmazyn_substrate`, shell, … |
| stage3 / full world | spójny prefix + (daleko) self-host |

## Zapisany postęp (wejście do Tora B)

To **nie** jest własny rustc — to **fundament freestanding**, bez którego Tor B nie ma sensu:

| ID | Artefakt | Stan |
|----|----------|------|
| R0–R1 | Z0 + docs | ✅ |
| R2 | `boot/kentry` Multiboot2 + marker | ✅ |
| R3 | `BumpAlloc` / limity slab | ✅ |
| R4 | feature `std` default | ✅ |
| R5 | `SlabStore` reach-GC + kentry `SLAB_OK` | ✅ |
| R6 | golden T×reach Store ↔ SlabStore | ✅ (test w substrate) |
| SF.2 | QEMU serial kentry | ⏳ opcjonalne (brak qemu w PATH dev) |
| G | pełniejszy freestanding Store | ⏳ następny kod OS |
| **TB.0** | decyzja: skąd **własny** kompilator | ⏳ ten dokument |
| **TB.1** | stage0 inventory + skrypt „build critical lib host→prefix” | ⏳ |
| **TB.2** | pierwszy pakiet przebudowany „od środka” | ❌ wymaga TB.0 tool |

## Decyzja TB.0 — skąd kompilator? (otwarte)

Budowa pełnego `rustc` od zera = lata. Realistyczne ścieżki (wybór świadomy, nie domyślny):

| Opcja | Opis | Koszt / ryzyko |
|-------|------|----------------|
| **A. stage0 = oficjalny rustc** | Zawsze budujemy world host-rustc; „Tor B” = tylko *layout* prefix/LFS skryptów, bez self-host | niski; **nie** domyka Gentoo |
| **B. mrustc → rustc** | Bootstrap historyczny: C++ mrustc kompiluje stary rustc, potem łańcuch w górę | duży; sprawdzony w ekosystemie |
| **C. gccrs / inny front** | Alternatywny front-end | niepewny maturity |
| **D. własny mini-kompilator** | Tylko podzbiór języka pod `no_std` / DSL Karmazyn | kontrola, ale **nie** kompiluje dzisiejszego substratu w Rust 2021 |
| **E. odroczenie** | Trzymać Tor A; freestanding G; Tor B gdy będzie decyzja A–D | **domyślne teraz** |

**Rekomendacja robocza (2026-08-06):** **E + równolegle A-lite**  
- Kontynuować freestanding (G) i golden law.  
- Opcjonalnie: `prefix/` installer (host rustc) jako *ćwiczenie LFS layout*, bez udawania self-host.  
- Nie obiecywać „własnego rustc” bez wybranej opcji B/C/D i osobnego budżetu.

## TB.1 — inventory stage0 (gdy ruszamy)

```text
host:    rustc, cargo, (gcc/link), opcjonalnie qemu
critical libs do przebudowy (kolejność):
  1. karmazyn_slab        (no_std, kentry)
  2. karmazyn_substrate   (std host + C ABI)
  3. karmazyn_shell
  4. boot/kentry          (x86_64-unknown-none)
out:     prefix/bin, prefix/lib, snap smoke
```

Skrypt Tora A już częściowo to robi: `native/bootstrap_from_scratch.ps1` (host tools only).

## Następny krok kodu (nie TB.0)

Z roadmapy OS (`rust_roadmap_tech.md`):

1. Utrzymać `cargo test` slab+substrate + golden R6.  
2. (opc.) QEMU SF.2 gdy qemu w PATH.  
3. Faza **G**: zbliżać host Store i slab (wspólne prawo już golden); freestanding bez HashMap.  
4. Tor B TB.0 — dopiero po jawnej decyzji użytkownika (A/B/C/D).

## Powiązania

- `BOOTSTRAP_STAGES.pl.md` — Tor A vs B  
- `rust_roadmap_tech.md` — R0…G  
- `boot/kentry/README.md` — R5 SLAB_OK  
- `native/stage1_verify.ps1` — bramka Tora A  

---

*Seed 2026-08-06 — kontynuacja zapisanego postępu Rust (R5→R6), nie start budowy rustc.*
