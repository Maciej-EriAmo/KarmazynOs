# KarmazynOS — Bootstrap Stages (from scratch)

**Status:** living · **Data:** 2026-08-06  
**Decyzja architektoniczna:** kanoniczną podstawą systemu jest jądro w Rustcie (host: zewnętrzny `rustc` + Cargo).

Powiązania: **`KANON.md`** (filtr kanon/host/plan), `rust_roadmap_tech.md`, `rust_substrate_map.md`, `TOR_B_TOOLCHAIN.pl.md`, `runtime_pl.md`, `native/`.

---

## Cel

Dwa toru — nie mylić:

### Tor A — produkt / runtime (to, co robimy teraz)
Rdzeń KarmazynOS (jądro + shell + podstawowe narzędzia) **uruchamia się** bez Pythona jako warstwy nośnej.  
Budowa nadal na **hostowym** `rustc` + Cargo. To są **milestone’y produktowe**, nie bootstrap Gentoo.

### Tor B — wzorzec Gentoo **i** Linux From Scratch (właściwa analogia)
To nie „mamy shell”, tylko **samopodnoszenie łańcucha narzędzi** — ten sam pomysł w dwóch szkołach:

> Za pomocą **własnych** narzędzi kompilujesz **ważne biblioteki** (i kolejne warstwy toolchainu), aż system przestaje zależeć od obcego kompilatora/hosta.

| Gentoo | Linux From Scratch (idea) | Sens wspólny |
|--------|---------------------------|--------------|
| **stage1** | host → tymczasowy toolchain / seed | minimalna baza, start przebudowy |
| **stage2** | chroot + przebudowa tooli i lib **już „wewnątrz”** | własne narzędzia składają kluczowe biblioteki |
| **stage3** | pełny system skompilowany we własnym łańcuchu | spójny world „od środka”, gotowy do pracy |

LFS robi to jawnie: najpierw budujesz toolchain na hoście, potem **wchodzisz w nowe środowisko** i **ponownie** kompilujesz ważne pakiety własnymi binarkami — żeby uciąć zależności od hosta (tzw. purity / self-contained build).  
Gentoo stage* to ta sama logika w postaci predefiniowanych obrazów stage.

**Tor B wystartował (TB.1):** własny kompilator **`kcc`** (K0→C) kompiluje krytyczne progi termiczne (`thermal.k0`).  
Edytor/OS/gcc-link mogą być obce; **frontend kompilatora jest nasz**.  
Host `rustc` = **stage0** (buduje `kcc`), nie kompilator krytycznego `.k0`.  
Reszta jądra w Rust nadal stage0 — Tor A / dług TB.2+.

| Tor A (dziś) | Tor B (Gentoo / LFS) |
|--------------|----------------------|
| Stage1 ✅ / shell milestone | **kcc** własny kompilator ✅ TB.1 |
| `bootstrap_from_scratch.ps1` (host rustc) | `thermal.k0` przez **kcc** ✅ |
| substrate/shell w Rust | kolejne lib w K0 ⏳; self-host kcc ⏳ |

Punkt startowy Tora A: `native/karmazyn_substrate` + `native/karmazyn_slab`.

---

## Stage 1 — Bootstrap (jądro jako niezależna jednostka) ✅ DONE · Tor A

**Cel (Tor A)**  
Rustowe jądro = fundament **w runtime**.  
Da się je zbudować (host rustc), przetestować i uruchomić **bez Pythona**.  
To **nie** jest Gentoo-stage1 (tam stage1 to start przebudowy *własnymi* narzędziami).

**Zakres**
- Pełne prawo systemu w Rustcie: atomy, temperatura, stany (HOT / WARM / COLD / TOMB), reach-GC, tick.
- Stabilne **C ABI** (`ksub_*`) jako jedyna oficjalna granica binarna (`include/karmazyn_substrate.h`).
- Minimalny program testowy (pure Rust **i** C): Store → atomy → tick+GC → stats.
- Python Store = referencja / golden tests.
- Bramka: `native/stage1_verify.ps1`.

**Kryterium wyjścia** ✅  
`cargo build --release` w katalogu jądra → działające jądro + testy; Python nie jest w ścieżce krytycznej **uruchomienia** prawa Store.

### Jak zbudować Stage 1 (bez Pythona)

```powershell
cd C:\Users\drwis\KarmazynOs
.\native\stage1_verify.ps1
# bez C:  .\native\stage1_verify.ps1 -SkipC
```

| Deliverable | Ścieżka |
|-------------|---------|
| Host Store + C ABI | `native/karmazyn_substrate` |
| Freestanding slab / reach-GC | `native/karmazyn_slab` |
| Pure Rust gate example | `examples/stage1_bootstrap.rs` |
| C ABI smoke | `native/c_smoke/stage1_c_smoke.c` |
| Verify script | `native/stage1_verify.ps1` |

**Bootstrap Level 1** — zamknięte 2026-08-06.

---

## Stage 2 — Native Shell + cienki most ⚡ MILESTONE · Tor A (nie Gentoo-stage2)

**Cel praktyczny (Tor A)**  
System da się **używać** bez Pythona: shell i podstawowe narzędzia na binarnym jądrze.

**Czym jest Gentoo-stage2 (Tor B) — dla porównania**  
Nie „mamy REPL”, tylko: **własnymi narzędziami** przebudowujesz / kompilujesz **ważne biblioteki** (u nas kandydaci: `karmazyn_slab`, `karmazyn_substrate`, shell, ewentualnie libc/SDK).  
Bez własnego kompilatora ten wzorzec **się nie domyka** — i nie udajemy, że shell to stage2 Gentoo.

**Zakres (runtime)**
- Shell w Rustcie na API jądra (dziś rlib; C ABI opcjonalnie później).
- Komendy: `stats`, atom, `tick`, stany, **save/load** (`KSUB_SNAP`).
- Python = opcjonalny klient (host product), nie warunek shella.
- Mały program C/Rust linkujący się do jądra — OK.

**Poza ścieżką krytyczną Stage 2**
- **Lua** — może poczekać; **nie jest warunkiem** Stage 2 ani bootstrapu 1–3.  
  Gdy wróci: gość na natywnym jądrze, nie przez Pythona — ale to osobny wątek.

**Milestone „używalne bez Pythona”** (osiągnięty, 2026-08-06) — *nie* mylić z zamknięciem stage:

| Element | Status |
|---------|--------|
| `native/karmazyn_shell` REPL | ✅ |
| Persist `save`/`load` (`KSUB_SNAP 1`) | ✅ |
| Batch `-e` / skrypt `.ksh` | ✅ (fail → exit ≠ 0) |
| `stage2_verify.ps1` | ✅ bramka |
| Python nie wymagany do sesji shell | ✅ |
| Shell tylko przez C ABI | opcjonalne, nie gate |
| Lua native | **odroczone** (nie warunek) |
| Własny rustc / self-host toolchain | ❌ → **dlatego brak zamknięcia Stage 2 „Gentoo”** |

```powershell
.\native\stage2_verify.ps1
cd native\karmazyn_shell
cargo run --release
# k$ save out\demo.ksub
# k$ load out\demo.ksub

cargo run --release -- -e "atom var x 50" -e "bubble r" -e "root 0" -e "bind 0 x 0" -e "save out\demo.ksub" -e quit
cargo run --release -- examples\smoke.ksh
```

---

## Stage 3 — Jednorodne środowisko 🚧 · Tor A starter / Tor B = daleko

**Cel praktyczny dziś (Tor A)**  
Jeden skrypt: host `rustc`+Cargo → jądro + shell + smoke — **bez Pythona**.  
To jest wygodny *from source on host tools*, nie Gentoo-stage3.

**Gentoo-stage3 (Tor B)**  
Spójne środowisko, w którym **ważne biblioteki i narzędzia** są skompilowane **własnym** łańcuchem i nadają się do dalszej pracy „od środka”.  
Wymaga najpierw własnych narzędzi (kompilator + enough of the world) — osobny, długi tor; nie checkbox przy shellu.

**Zakres praktyczny**
1. buduje jądro,
2. buduje shell,
3. smoke (save/load),
4. (później) prefix install / `.sh`.

Wyższe warstwy (Cynober / KarminQL / Lua / analityka) *na* fundamencie — nie warunek Stage 3 starter.

```powershell
.\native\verify_rebuild.ps1
# → REBUILD_OK  (wzorzec: rustc, bez gcc)

.\native\bootstrap_from_scratch.ps1
# → REBUILD_OK + STAGE2_VERIFY_OK + BOOTSTRAP_FROM_SCRATCH_OK
# Wymaga host rustc+cargo. Nie wymaga Pythona. Nie jest self-host rustc.

# Unix:
# ./native/bootstrap_from_scratch.sh

# Prefix (bin/shell + include + lib):
.\native\install_prefix.ps1
# → dist\prefix\
```

| Element | Status |
|---------|--------|
| `bootstrap_from_scratch.ps1` | ✅ starter na obcym rustc (+ stage2_verify) |
| `bootstrap_from_scratch.sh` | ✅ |
| `install_prefix.ps1` | ✅ `dist/prefix` |
| Własny rustc w systemie | ❌ poza horyzontem „zamknij stage” |

---

## Podsumowanie

| Etykieta w repo | Tor | Co to naprawdę | Status |
|-----------------|-----|----------------|--------|
| Stage 1 | A | Runtime: jądro/prawo Store bez Pythona | ✅ DONE |
| Stage 2 (shell+snap) | A | Runtime: używalność bez Pythona | ⚡ milestone + `stage2_verify` |
| `bootstrap_from_scratch` | A | Build na **host** rustc, bez Pythona | ✅ starter (+ `.sh`, prefix) |
| Gentoo stage1–3 / LFS toolchain→rebuild | B | **rustc** składa crate’y (slab→substrate→shell→kcc) | ✅ `verify_rebuild` → `REBUILD_OK`; kcc/K0 = minister, nie slot gcc |

**Dzisiaj (2026-08-06):**  
Tor A: Stage1 + shell/`KSUB_SNAP`.  
Tor B (prawdziwy wzorzec Gentoo): **nie mylić z milestone’ami** — wymaga własnych narzędzi do kompilacji kluczowych lib.  
Lua nie blokuje żadnego toru.

---

## Zasada decyzyjna

1. **Python-nośny w runtime?** → poza Torem A (chyba że golden/test).  
2. **Lua / goście?** → opcjonalne; nie warunek.  
3. **„Czy to Gentoo stage N / faza LFS?”** → tylko jeśli **rustc** przebudowuje ważne **crate’y** (`verify_rebuild`). Shell sam ≠ stage2 Gentoo. kcc/K0 ≠ slot gcc.  
4. **„Czy milestone Tor A?”** → osobne pytanie (używalność, bramki `stage1_verify`).

---

*Dokument żywy. Aktualizacja 2026-08-19 — Tor A: stage2; Tor B wzorzec: rustc/crates (`verify_rebuild`). kcc = minister.*


