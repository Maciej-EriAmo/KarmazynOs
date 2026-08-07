# KarmazynOs — KANON (co jest kanonem, hostem, planem)

**Status:** living · **Data:** 2026-08-07  
**Po co ten plik:** jedna strona, żeby filozofia, kod i narracja nie rozjeżdżały się.  
Nie zastępuje `README.md` / `philosophy.pl.md` / `BOOTSTRAP_STAGES.pl.md` — **filtruje**, co wolno twierdzić.

---

## 0. Model (bez zamętu)

```
                    ┌─────────────────────────────┐
                    │  CIENKIE WARSTWY (języki)    │
                    │  Python · Lua · shell · Lisp │
                    │  Studio · kcc · nawet „app”  │
                    │  w Rust poza jądrem          │
                    └─────────────┬───────────────┘
                                  │ woła / linkuje
                    ┌─────────────▼───────────────┐
                    │  RUST = KOŚCI + WYKONANIE   │
                    │  implementacja silnika,     │
                    │  rlib / cdylib / C ABI      │
                    └─────────────┬───────────────┘
                                  │ jest
                    ┌─────────────▼───────────────┐
                    │  SUBSTRAT = JEDYNY SILNIK   │
                    │  rządzi wszystkim           │
                    │  Store · T×reach · prawo    │
                    └─────────────────────────────┘
```

| Byt | Rola | Nie jest |
|-----|------|----------|
| **Substrat** | **Jedyny silnik.** Prawo: atomy, T, bąble, roots, reach-GC. Wszystko inne jest klientem. | Językiem aplikacji |
| **Rust** | **Kości i warstwa wykonawcza** substratu (oraz cienkie narzędzia: shell, kentry, kcc-stage0). | „Konkurencyjnym jądrem” obok substratu |
| **Python / Lua / Lisp / Studio / …** | **Cienkie warstwy** — składnia, I/O, UX, skrypty. Wołają silnik (native DLL / rlib / C ABI). | Silnikiem; nie rządzą prawem Store |
| **Python Store (legacy)** | Referencja / golden / rescue — **to samo prawo**, nie drugi król | Domyślnym władcą (default = native) |

**Zasady wynikające z modelu:**

1. **Substrat rządzi** — reguły T×reach są w jednym miejscu; języki ich nie redefiniują.  
2. **Języki / userspace są cienkie** — ten sam status: **klient silnika**, nie współwłaściciel prawa.  
3. **Atomy i bąble są niżej** — żyją **w substracie (jądro)**. Userspace ich **nie „widzi”** jako swojego modelu świata; widzi efekt (API produktu, I/O, skrypt).  
4. **CPython / Lua / Studio / shell-app** — klienci; nie konkurują z jądrem.  
5. **Tor A/B** — dostarczenie i kompilacja wokół silnika, nie zamienniki silnika.

### Userspace = klient (klasycznie)

```
  userspace / narzędzia     nie trzymają prawdy o A/B
       │  wołają (opcjonalnie) fasadę / API
       │  NIE są właścicielem atomów i bąbli
  ───────┼───────────────────────────────────
  jądro / substrat          ATOMY · BĄBLE · T · reach
                            tu jest model; tu GC; tu prawo
```

| Poziom | Widzi | Nie jest |
|--------|--------|----------|
| **Userspace** | to, co warstwa produktu/API wystawi (ekran, plik, wynik skryptu) | magazynem atomów/bąbli |
| **Jądro (substrat)** | A, bąble, roots, T, reach | „aplikacją” |

**Shell / `ksub_*` / diagnostic REPL** — to **uprzywilejowany operator jądra** (okno serwisowe), nie wzorzec „każdy userspace mówi atom/bind”.  
Product userspace powinien iść **wyżej** (zadania, widoki, gość), a nie kopiować modelu jądra do każdego skryptu.

**Wniosek:** userspace jest **takim samym klientem substratu** jak inna cienka warstwa — tylko z innej strony (UX). Nie ma osobnego „userspace Store”.

### Król i ministrowie

| Rola | Kto | Wolno |
|------|-----|--------|
| **Król** | **tylko substrat** (prawo A/B/T/reach) | stanowi prawo, trzyma prawdę stanu |
| **Minister** | Karmin_DB, Holon, Studio, shell, Lua, Python, kcc, Cynober wire… | służy, zarządza domeną, woła króla przez szwy |
| **Uzurpator** (zakaz) | cokolwiek z własnym „Store prawdy” obok jądra | — |

- **Karmin_DB** = minister skarbu (trwałość, KarminQL, sieć) — **nie** król.  
- **Holon** = minister pamięci SE (handoff) — **nie** baza-król.  
- **Studio / boot / języki** = ministrowie dworu i posłowie — cienkie warstwy.  
- **Shell / `ksub_*`** = minister spraw wewnętrznych / adjutant (sys) — bliżej tronu, nadal **nie** król.

**Reszta ma działać tak samo jak DB:** łączy się **szwami** z jądrem, co najwyżej jako minister — nigdy jako drugi król.

```
information = stabilization( H ∘ P ∘ A )     # wizja (README)
prawo silnika (kod):  T = KIEDY · reach = CZY
```

KarmazynOs to **przestrzeń informacji napędzana substratem** —  
**nie** bootowalny „pełny OS” (dopóki L2+ nie jest w KANON z bramką).

---

## 1. Trzy półki (nie mylić z warstwami silnika)

Półki = **co wolno twierdzić**. Warstwy = **kto rządzi**.

| Półka | Znaczenie | Wolno mówić |
|-------|-----------|-------------|
| **KANON** | Substrat + bramki; regresja = błąd | „mamy”, „domknięte”, `*_VERIFY_OK` |
| **HOST** | Cienka warstwa na maszynie dev (Studio, boot.py, SDL) | „działa na hoście”, nie „samodzielny OS” |
| **PLAN** | Docs, roadmap, szkielety | „plan”, „papier”, „nie wdrożone” |

**Zasada Z0 (PROJECT.md):** nie mówić „mamy GRUB / ISO / desktop OS”, dopóki to nie jest w **KANON** z bramką.

---

## 2. KANON — silnik (substrat, Tor A Stage 1)

**Formuła:** temperatura mówi **kiedy**, osiągalność mówi **czy**.

| Stan | Reach | Skutek |
|------|-------|--------|
| żywy (T ≥ TOMB) | dowolny | atom istnieje |
| zimny / TOMB | **osiągalny** (root/bind/…) | **retained TOMB** |
| zimny / TOMB | **nieosiągalny** | **vacuum** (GC / reap) |

**Gdzie jest kanon (implementacja):**

| Artefakt | Rola |
|----------|------|
| `native/karmazyn_slab` | freestanding / no_std — to samo prawo |
| `native/karmazyn_substrate` | **silnik** host: Store + **C ABI** `ksub_*` (Rust = kości) |
| `native/c_smoke/*` | cienka warstwa C na silniku |
| `native/stage1_verify.ps1` | bramka Stage 1 |
| Python `Store` | cienka / golden kopia prawa — **nie** konkurencyjny silnik |

**Bramka:** `.\native\stage1_verify.ps1` → `STAGE1_VERIFY_OK`.

**Termika (kanon implementacji):**  
- odczyt / `heat` / `lookup` (thermal) → `HEAT_READ`  
- zapis tokena (`set_value` / `setval`) → `HEAT_WRITE` (mniejszy ΔT)  
- `set_t` = absolutne T bez licznika heat  

**Świadomie poza kanonem Stage 1:** HRR, pryzmaty Warp Oblivion, Ring-LWE archiwum, pełne Φ — to wizja / warstwy wyżej.

---

## 3. KANON — cienka warstwa bez Pythona (Tor A Stage 2)

**Cel:** **używać silnika** bez CPythona (shell + snapshot) — shell nie jest silnikiem.

| Artefakt | Rola |
|----------|------|
| `native/karmazyn_shell` (0.3.2+) | cienka warstwa REPL/batch na rlib Store |
| `examples/lifecycle.ksh` | to samo prawo T×reach przez shell |
| `KSUB_SNAP` | persist stanu **silnika** |
| `native/stage2_verify.ps1` | bramka Stage 2 |

**Bramka:** `.\native\stage2_verify.ps1` → `STAGE2_VERIFY_OK`.

**To NIE jest Gentoo-stage2** i **nie jest jądrem**.  
Shell / Lisp / Lua / Python = klienci substratu.

---

## 4. KANON — własny kompilator (Tor B)

**Cel:** ważne prawo / lib w **K0** kompiluje **kcc** (nasz frontend), nie „cały świat w rustc”.

| Zasada | |
|--------|--|
| **Własne** | lex/parse/sem/codegen kcc, źródła `.k0` |
| **Obce OK** | stage0 `rustc` (tylko buduje kcc), `gcc`/`cc` jako link, edytor, OS |
| **Nie udajemy** | pełnego self-host kcc, dopóki TB.4 Phase 4 nie ma bramki |

| Artefakt | Rola |
|----------|------|
| `toolchain/kcc` (0.6.1+) | K0 → C99 |
| `examples/*.k0` | thermal, store_mini, struct_point, … |
| `toolchain/kcc_selfhost/` | TB.4 Phase **0–3** (lex → parse → IR/sem/emit/eval) |
| `toolchain/verify_kcc.ps1` | bramka Tor B |

**Bramka:** `.\toolchain\verify_kcc.ps1` → `KCC_VERIFY_OK`.

**TB.4 Phase 4** (dump C → pętla self-host) = **PLAN**, nie kanon, dopóki nie ma `verify_selfhost` zielonego.

---

## 5. HOST — cienkie warstwy product (L1)

To **nie silnik**. To skóra na hoście: boot, Studio, skrypty.  
**Musi** wołać substrat (`KARMAZYN_SUBSTRATE=native` = właściwa droga).

| Obszar | Path (orientacyjnie) |
|--------|----------------------|
| Boot / REPL host | `software/karmazyn_boot.py`, root mirror |
| Studio SDL | `karmazyn_studio.py` |
| Lua / mini-Lisp / … | goście — cienkie języki na Store |
| Holon (pamięć SE) | **Karmin_Ae** — osobny produkt; nie silnik Karmazyn |

**Uczciwe sformułowania:**  
„cienka warstwa / Studio / gość na substracie”.  
**Nie:** „jądro w Pythonie”, „CPython rządzi Karmazynem”, „samodzielny OS”.

---

## 6. PLAN — papier i szkielety

| Temat | Status narracji |
|-------|-----------------|
| GRUB → Linux → Karmazyn (ISO/VM) | plan Tor A boot |
| Multiboot `kentry` pełny Store | marker / szkielet ≠ pełne jądro bare-metal |
| Self-host kcc (TB.4 P4+) | Phase 0–3 seed; P4 odłożone |
| Own backend bez gcc (TB.5) | daleko |
| Pełne HRR / pryzmaty w native | wizja; nie Stage 1–2 |
| Starlink / product demos | poza gate A/B substratu |

Plany: `grub_loader_plan.md`, `BOOTSTRAP_STAGES.pl.md`, `TOR_B_TOOLCHAIN.pl.md`, `rust_roadmap_tech.md`.

---

## 7. Filozofia vs poziomy języka

| Poziom | „Błąd” | Sens w Karmazynie |
|--------|--------|-------------------|
| **Informacja (atom)** | nie ma „exception” jako bytu | jest **zanik** (vacuum) / **TOMB** |
| **Narzędzie (shell, kcc, CI)** | exit ≠ 0, assert, `Err` | awaria **narzędzia**, nie atomu |
| **Pryzmat (wizja)** | brak dostępu | świat w którym dane **nie istnieją** (Warp Oblivion) — nie Stage 2 shell |

Shell ma pełny wgląd w Store, bo to **operator jądra**, nie agent z pryzmatem OUT.

---

## 8. Obce vs własne (ściągawka)

| Własne (budować / strzec) | Obce (wolno używać) |
|---------------------------|---------------------|
| Prawo T×reach w slab/substrate | `rustc` / Cargo jako **stage0** |
| kcc frontend + `.k0` krytyczne | `gcc`/`clang` **link** |
| shell Stage 2, C ABI | edytor, OS, IDE |
| bramki `stage1` / `stage2` / `verify_kcc` | GitHub Actions runner |

---

## 9. Bramki (kanon operacyjny)

```powershell
cd C:\Users\drwis\KarmazynOs

.\native\stage1_verify.ps1      # STAGE1_VERIFY_OK  — prawo + C ABI
.\native\stage2_verify.ps1      # STAGE2_VERIFY_OK  — shell + lifecycle
.\toolchain\verify_kcc.ps1      # KCC_VERIFY_OK     — Tor B + TB.4 P0–3

# CI (gate-product): slab + substrate + kcc unit + Python unittest + kentry
# Nie zastępuje pełnego verify_kcc / stage2 na Windows.
```

---

## 10. Priorytety (ustalone 2026-08-07)

1. **Konsolidacja** — bramki zielone, nie drift  
2. **Tor A używalność** — shell (domknięty 0.3.2 + lifecycle)  
3. **CI** — tarcza, bez rozdmuchiwania na siłę  
4. **TB.4 Phase 4** — odłożone (świadomie)  
5. **Product** (Starlink/SDL/…) — poza gate substratu  

---

## 11. Zakazy narracyjne

1. Mówić, że **język** (Python, Lua, Lisp, Julia…) **rządzi** — rządzi tylko **substrat**.  
2. Mówić „jądro w CPython” / „przejście na Rust” tak, jakby silnika jeszcze nie było — **silnik już jest (substrat w Rust)**.  
3. Nazywać shell **Gentoo-stage2** albo „OS”.  
4. Twierdzić „self-host kcc” bez Phase 4 + bramki.  
5. Traktować Python Store jako konkurencyjny silnik (to cienka / golden warstwa).  
6. Mieszać **Karmin_Ae** z substratem KarmazynOs.

---

## 12. Mapa plików (start)

| Chcę… | Idź do |
|-------|--------|
| Filozofia długa | `philosophy.pl.md`, `README.md` (root) |
| Bootstrap / tory | `BOOTSTRAP_STAGES.pl.md` |
| Tor B kcc | `TOR_B_TOOLCHAIN.pl.md`, `toolchain/kcc/README.md` |
| Arch runtime monorepo | `ARCHITECTURE.md` §5, `runtime_pl.md` |
| Kontynuacja sesji | `SESSION_CONTINUE.md` |
| **Ten filtr** | **`KANON.md`** (tu) |

---

*Aktualizuj ten plik, gdy coś awansuje z PLAN → KANON (z bramką) albo gdy świadomie zmieniasz priorytety.  
Nie rozdmuchuj — jedna strona prawdy.*
