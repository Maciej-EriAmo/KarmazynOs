# KarmazynOS — Bootstrap Stages (from scratch)

**Status:** living · **Data:** 2026-08-06  
**Decyzja architektoniczna:** kanoniczną podstawą systemu jest jądro w Rustcie (host: zewnętrzny `rustc` + Cargo).

Powiązania: `rust_roadmap_tech.md`, `rust_substrate_map.md`, `runtime_pl.md`, `native/`.

---

## Cel

Zbudować **jednorodne środowisko**, w którym rdzeń KarmazynOS (jądro + Shell + podstawowe narzędzia) da się odtworzyć z jednego, spójnego łańcucha narzędziowego — **bez Pythona** jako warstwy nośnej.

Analogia do klasycznego bootstrapu Gentoo (stage1 → stage2 → stage3):
nie bierzemy gotowego obrazu, tylko podnosimy istniejącą podstawę do pełnej samodzielności.

**Uczciwa granica analogii:**  
Gentoo stage* domyka się dopiero gdy łańcuch narzędziowy jest **własny** (kompilator w systemie).  
KarmazynOS **nie ma własnego `rustc`**. Dlatego:

| Co da się domknąć dziś | Czego **nie** da się domknąć bez własnego kompilatora |
|------------------------|--------------------------------------------------------|
| Stage 1: jądro + C ABI bez Pythona | „Stage 2 zamknięty” w sensie Gentoo (samodzielność toolchainu) |
| Milestone: native shell + snapshot | Stage 3 jako pełny self-host (system buduje siebie *własnym* rustc) |
| Skrypt `bootstrap_from_scratch` na **obcym** rustc+Cargo | Odtwarzalność bez zewnętrznego toolchainu |

Stage 2/3 poniżej opisują **kierunek** i **kamienie milowe**, nie checkbox „DONE = koniec pracy”.

Punkt startowy (Stage 1 done): `native/karmazyn_substrate` + `native/karmazyn_slab`.

---

## Stage 1 — Bootstrap (jądro jako niezależna jednostka) ✅ DONE

**Cel**  
Rustowe jądro staje się prawdziwym, samodzielnym fundamentem **w runtime**.  
Da się je zbudować, przetestować i uruchomić **bez Pythona**.  
(Budowa nadal wymaga hostowego `rustc` + Cargo — to OK dla Stage 1.)

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

## Stage 2 — Native Shell + cienki most ⚡ MILESTONE (nie „zamknięcie”)

**Cel praktyczny**  
System da się **używać** bez Pythona: shell i podstawowe narzędzia na binarnym jądrze.

**Czego Stage 2 *nie* jest**  
- Nie jest domknięciem bootstrapu w sensie Gentoo.  
- **Nie ma twardego „Stage 2 DONE”**, dopóki nie ma **własnego kompilatora Rust** (lub świadomej, osobnej decyzji o self-host toolchianie).  
  Bez tego zawsze budujemy shell/kernel na **obcym** `rustc` — milestone runtime jest realny, „zamknięcie stage2” jako samodzielność łańcucha — **nie istnieje** w obecnym stanie projektu.

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

## Stage 3 — Jednorodne środowisko („from scratch”) 🚧 na obcym toolchainie

**Cel praktyczny (dziś)**  
Jeden skrypt: od `rustc`+Cargo hosta → jądro + shell + smoke — **bez Pythona**.

**Cel daleki (self-host)**  
Rdzeń buduje się **własnym** łańcuchem. To wymaga kompilatora (Rust lub inny wybrany) *wewnątrz* KarmazynOS — **osobny, wieloletni tor**, nie checkbox przy shellu.

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

| Stage | Nazwa | Sensowny wynik dziś | Status |
|-------|--------|---------------------|--------|
| 1 | Bootstrap | Jądro + C ABI bez Pythona w runtime | ✅ DONE |
| 2 | Native Shell | Używalność bez Pythona (shell+snap) | ⚡ milestone; **brak zamknięcia** (brak własnego rustc) |
| 3 | Homogeneous | From-scratch na host rustc; self-host = później | 🚧 starter |

**Dzisiaj (2026-08-06):**  
Stage 1 domknięty. Stage 2 ma milestone runtime (shell + `KSUB_SNAP`), ale **nie zamykamy Stage 2** — brak własnego kompilatora Rust.  
Lua nie blokuje. Dalsza praca bootstrapu: utrzymać Stage 1 gate, szlifować shell/prefix gdy potrzeba; self-host toolchain = osobna decyzja.

---

## Zasada decyzyjna

1. **Python-nośny?** → nie należy do Bootstrap 1–3 (chyba że golden/test).  
2. **Lua / goście?** → opcjonalne; nie warunek zamknięcia stage.  
3. **„Czy stage2/3 DONE?”** → bez własnego kompilatora odpowiedź na pełne zamknięcie jest **nie**; pytaj o milestone runtime, nie o Gentoo-final.

---

*Dokument żywy. Aktualizacja 2026-08-06 — korekta: Stage 2 nie zamyka się bez własnego rustc; Lua odroczona.*
