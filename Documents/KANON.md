# KarmazynOs — KANON (co jest kanonem, hostem, planem)

**Status:** living · **Data:** 2026-08-07  
**Po co ten plik:** jedna strona, żeby filozofia, kod i narracja nie rozjeżdżały się.  
Nie zastępuje `README.md` / `philosophy.pl.md` / `BOOTSTRAP_STAGES.pl.md` — **filtruje**, co wolno twierdzić.

---

## 0. Jedno zdanie

KarmazynOs to **przestrzeń dynamicznej informacji** z prawem termodynamicznym w substracie —  
**nie** bootowalny „pełny OS” (dopóki L2+ nie jest zrobione i nie kłamiemy w bannerach).

```
information = stabilization( H ∘ P ∘ A )     # wizja (README)
prawo jądra (dziś w kodzie):  T = KIEDY · reach = CZY
```

---

## 1. Trzy półki (nie mylić)

| Półka | Znaczenie | Wolno mówić |
|-------|-----------|-------------|
| **KANON** | Obowiązuje w kodzie bramek; regresja = błąd | „mamy”, „domknięte”, `*_VERIFY_OK` |
| **HOST** | Product / dev na maszynie użytkownika; może używać Pythona, SDL, Lua | „działa na hoście”, nie „samodzielny OS” |
| **PLAN** | Docs, roadmap, szkielety | „plan”, „papier”, „nie wdrożone” |

**Zasada Z0 (PROJECT.md):** nie mówić „mamy GRUB / ISO / desktop OS”, dopóki to nie jest w **KANON** z bramką.

---

## 2. KANON — prawo substratu (Tor A Stage 1)

**Formuła:** temperatura mówi **kiedy**, osiągalność mówi **czy**.

| Stan | Reach | Skutek |
|------|-------|--------|
| żywy (T ≥ TOMB) | dowolny | atom istnieje |
| zimny / TOMB | **osiągalny** (root/bind/…) | **retained TOMB** |
| zimny / TOMB | **nieosiągalny** | **vacuum** (GC / reap) |

**Gdzie jest kanon (implementacja):**

| Artefakt | Rola |
|----------|------|
| `native/karmazyn_slab` | freestanding / no_std, to samo prawo |
| `native/karmazyn_substrate` | host Store + **C ABI** `ksub_*` |
| `native/c_smoke/*` | C bez Pythona |
| `native/stage1_verify.ps1` | bramka Stage 1 |
| Python `Store` | **referencja / golden**, nie nośnik Stage 1 |

**Bramka:** `.\native\stage1_verify.ps1` → `STAGE1_VERIFY_OK`.

**Świadomie poza kanonem Stage 1:** HRR, pryzmaty Warp Oblivion, Ring-LWE archiwum, pełne Φ — to wizja / warstwy wyżej.

---

## 3. KANON — używalność bez Pythona (Tor A Stage 2)

**Cel:** system da się **używać** na binarnym jądrze (shell + snapshot).

| Artefakt | Rola |
|----------|------|
| `native/karmazyn_shell` (0.3.2+) | REPL / batch / assert / save-load |
| `examples/lifecycle.ksh` | **to samo prawo T×reach** w skrypcie shella |
| `KSUB_SNAP` | persist Store (atoms, bubbles, binds, roots) |
| `native/stage2_verify.ps1` | bramka Stage 2 |

**Bramka:** `.\native\stage2_verify.ps1` → `STAGE2_VERIFY_OK`.

**To NIE jest Gentoo-stage2.**  
Gentoo/LFS-stage2 = *własnymi narzędziami* przebudowujesz biblioteki. Shell = **Tor A runtime**.

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

## 5. HOST — product (L1)

Działa na hoście; **może** zależeć od Pythona / pygame / Lua. Nie jest warunkiem Stage 1–2.

| Obszar | Path (orientacyjnie) |
|--------|----------------------|
| Boot / REPL host | `software/karmazyn_boot.py`, root mirror |
| Studio SDL | `karmazyn_studio.py` |
| Guest Lua | `LUA/`, `lua_bin/` |
| Substrat z Pythona | `KARMAZYN_SUBSTRATE=native\|python` |
| Holon (pamięć SE) | osobny workspace **Karmin_Ae** — nie mylić z jądrem |

**Uczciwe sformułowania:**  
„Product host runtime”, „dev-boot”, „Studio na hoście”.  
**Nie:** „samodzielny system operacyjny”.

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

1. Mówić „mamy OS / GRUB / bare-metal Store”, gdy jest tylko host + marker.  
2. Nazywać shell **Gentoo-stage2**.  
3. Twierdzić „self-host kcc”, bez Phase 4 + bramki.  
4. Traktować Python Store jako **jedyny** kanon (native jest default substratu).  
5. Mieszać **Karmin_Ae (pamięć SE)** z jądrem KarmazynOs.

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
