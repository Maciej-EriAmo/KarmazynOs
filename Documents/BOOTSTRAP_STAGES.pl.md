# KarmazynOS — Bootstrap Stages (from scratch)

**Status:** living · **Data:** 2026-08-06  
**Decyzja architektoniczna:** kanoniczną podstawą systemu jest jądro w Rustcie (host: zewnętrzny `rustc` + Cargo).

Powiązania: `rust_roadmap_tech.md`, `rust_substrate_map.md`, `runtime_pl.md`, `native/`.

---

## Cel

Dwa toru — nie mylić:

### Tor A — produkt / runtime (to, co robimy teraz)
Rdzeń KarmazynOS (jądro + shell + podstawowe narzędzia) **uruchamia się** bez Pythona jako warstwy nośnej.  
Budowa nadal na **hostowym** `rustc` + Cargo. To są **milestone’y produktowe**, nie bootstrap Gentoo.

### Tor B — wzorzec Gentoo stage 1 → 2 → 3 (właściwa analogia)
W Gentoo stage* to nie „mamy shell”, tylko **wzorzec samopodnoszenia łańcucha narzędzi**:

> Za pomocą **własnych** narzędzi kompilujesz **ważne biblioteki** (i kolejne warstwy toolchainu), aż system przestaje zależeć od obcego kompilatora/hosta.

| Gentoo (idea) | Sens |
|---------------|------|
| **stage1** | Minimalna baza + start przebudowy — dopiero wznosisz narzędzia |
| **stage2** | Przebudowa kluczowych lib/tooli **już własnym** łańcuchem |
| **stage3** | Spójne środowisko: ważne biblioteki i narzędzia skompilowane „od środka”, gotowe do dalszej pracy |

**KarmazynOS dziś nie jest na torze B w domknięciu:** nie ma **własnego** kompilatora (rustc ani innego kanonicznego).  
Dopóki kompilacja jądra/shell/lib idzie wyłącznie hostowym `rustc`, jesteśmy w **Torze A**.  
Nazwy „Stage 1/2/3” w tym pliku historycznie opisują milestone’y Tora A; **prawdziwy** stage2/3 w sensie Gentoo zaczyna się dopiero, gdy *własne narzędzia* budują ważne biblioteki (substrate, slab, shell, potem reszta).

| Tor A (dziś) | Tor B (Gentoo-wzorzec) — wymaga własnego toolchiana |
|--------------|------------------------------------------------------|
| Stage1 ✅: prawo Store bez Pythona w runtime | stage1: minimalny seed + start własnych narzędzi |
| Shell + `KSUB_SNAP` = milestone używalności | stage2: własne narzędzia kompilują kluczowe lib |
| `bootstrap_from_scratch.ps1` na obcym rustc | stage3: spójny world zbudowany własnym łańcuchem |

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
| Batch `-e` / skrypt | ✅ |
| Python nie wymagany do sesji shell | ✅ |
| Shell tylko przez C ABI | opcjonalne, nie gate |
| Lua native | **odroczone** (nie warunek) |
| Własny rustc / self-host toolchain | ❌ → **dlatego brak zamknięcia Stage 2** |

```powershell
cd native\karmazyn_shell
cargo run --release
# k$ save out\demo.ksub
# k$ load out\demo.ksub

cargo run --release -- -e "atom var x 50" -e "bubble r" -e "root 0" -e "bind 0 x 0" -e "save out\demo.ksub" -e quit
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
.\native\bootstrap_from_scratch.ps1
# → STAGE1_VERIFY_OK + shell + BOOTSTRAP_FROM_SCRATCH_OK
# Wymaga host rustc+cargo. Nie wymaga Pythona. Nie jest self-host rustc.
```

| Element | Status |
|---------|--------|
| `bootstrap_from_scratch.ps1` | ✅ starter na obcym rustc |
| prefix install | ❌ TODO (gdy potrzeba) |
| `.sh` | ❌ TODO |
| Własny rustc w systemie | ❌ poza horyzontem „zamknij stage” |

---

## Podsumowanie

| Etykieta w repo | Tor | Co to naprawdę | Status |
|-----------------|-----|----------------|--------|
| Stage 1 | A | Runtime: jądro/prawo Store bez Pythona | ✅ DONE |
| Stage 2 (shell+snap) | A | Runtime: używalność bez Pythona | ⚡ milestone |
| `bootstrap_from_scratch` | A | Build na **host** rustc, bez Pythona | 🚧 starter |
| Gentoo stage1–3 | B | **Własne narzędzia** → kompilacja **ważnych bibliotek** | ❌ nie rozpoczęty (brak własnego kompilatora) |

**Dzisiaj (2026-08-06):**  
Tor A: Stage1 + shell/`KSUB_SNAP`.  
Tor B (prawdziwy wzorzec Gentoo): **nie mylić z milestone’ami** — wymaga własnych narzędzi do kompilacji kluczowych lib.  
Lua nie blokuje żadnego toru.

---

## Zasada decyzyjna

1. **Python-nośny w runtime?** → poza Torem A (chyba że golden/test).  
2. **Lua / goście?** → opcjonalne; nie warunek.  
3. **„Czy to Gentoo stage N?”** → tylko jeśli **własne narzędzia** kompilują ważne biblioteki. Shell na host-rustc ≠ stage2 Gentoo.  
4. **„Czy milestone Tor A?”** → osobne pytanie (używalność, bramki `stage1_verify`).

---

*Dokument żywy. Aktualizacja 2026-08-06 — wzorzec Gentoo = własne tooly → ważne lib; Tor A ≠ Tor B.*

