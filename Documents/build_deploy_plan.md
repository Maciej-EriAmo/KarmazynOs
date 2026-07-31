# Plan budowy i wdrożenia KarmazynOs

**Status:** plan roboczy · **L1 host:** gate + `scripts/dry_run_l1.ps1` (2026-07-31)  
**Data:** 2026-07-31  
**Wzór:** Gentoo stages + Dual-track (Product native / Lab python)  
**Kompilator Product:** `rustc` + cargo · **Mapa:** `rust_substrate_map.md`  
**Język:** L2+ (GRUB/ISO/kentry) = plan, nie nośnik — nie raportować jako „done”.

Powiązania: `io_stage1.md`, `studio_sdl.md`, `grub_loader_plan.md`, `runtime_pl.md`, `VERSION.txt`.

---

## 0. Cel wdrożenia

Dostarczyć **działający Product path**:

```
zbudowany substrat Rust (default)
  → boot z matrycą I/O Stage 1 (twarde FAIL jeśli brak)
  → gość Lua + host API + lua_bin
  → opcjonalnie Studio SDL (mapa T tło, prompt pełne okno)
  → (później) GRUB / ISO / kentry
```

**Nie-cel na ten plan:** pełny bare-metal OS w jednej iteracji; Secure Boot; sieć bąblowa L0.

---

## 1. Zasady (twarde)

| # | Zasada |
|---|--------|
| Z0 | **Rust pisze od razu pod substrat** — źródło prawdy prawa T×reach×GC to crate `native/karmazyn_substrate` (patrz §1.1) |
| Z1 | **Rust = Product Store**; Python = referencja / golden / rescue |
| Z2 | **Brak cichej degradacji** na ścieżce Product (Stage 1: FAIL, nie WARN) |
| Z3 | **Jeden gate = jedna komenda** (skrypt lub unittest) z exit 0/1 |
| Z4 | **Id w Rust = u32**; nazwy logiczne tylko w hoście (`name_to_aid`) |
| Z5 | **kernel_boundary**: jadro ↛ software |
| Z6 | Wdrożenie = **artefakt + gate + dokument wersji**, nie „działa u mnie” |

### 1.1 Z0 — Rust od razu pod substrat (nienegocjowalne)

**Sens:** nowa semantyka jądra **nie** powstaje „w Pythonie, a potem przeniesiemy do Rusta”.  
Powstaje **w crate substratu** (`atom.rs` / `store.rs` / ewentualnie nowy moduł w tym crate).  
Python, PyO3, ctypes, Studio, Lua — to **szwy i goście**, nie miejsce definicji prawa.

| Wolno w Rust substrate | Nie wolno w Rust substrate |
|------------------------|----------------------------|
| atomy, T, bąble, roots, tick, GC | UI, SDL, pygame |
| C ABI `ksub_*`, pure rlib API | parser Lua, shell meta |
| haki `env_of` / `extra_reach` (typy callback) | treść aplikacji, BootConfig UI |
| ewolucja pod `no_std` / kentry (ten sam model) | „tymczasowa” logika GC tylko w Pythonie |

**Kolejność implementacji (obowiązkowa):**

```
1. zmiana prawa / API w native/karmazyn_substrate (Rust)
2. cargo test  (gate substratu)
3. FFI / PyO3 tylko jeśli szew się zmienia
4. lustrzane dostosowanie Python reference (golden) — nie odwrotnie
5. host (thermal, boot, studio) — adaptacja do API
```

**Zakazane antywzorce:**

- feature „najpierw działa na PythonStore, Rust dogonimy”  
- logika GC/tick w `NativeStore` (Python) zamiast w `store.rs`  
- nowe progi T tylko w `karmazyn_atom.py` bez `atom.rs`  
- id string w core „bo tak wygodniej w Lua”

**Punkt sukcesu Z0 (ciągły):**

| ID | Punkt sukcesu |
|----|----------------|
| **SZ0.1** | Każdy PR zmieniający prawo Store **dotyka** `native/karmazyn_substrate/src/*` |
| **SZ0.2** | `cargo test` przechodzi **przed** scaleniem hosta |
| **SZ0.3** | Python reference jest **zsynchronizowany** z Rust (compat), nie prowadzi |
| **SZ0.4** | Review: brak nowej semantyki GC wyłącznie w plikach `software/` lub samym `*_native.py` |

---

## 2. Stan obecny (baseline — punkt startu)

| Element | Stan | Wersja / gate |
|---------|------|----------------|
| Kernel fasada | ✅ | 1.1.0 |
| Native Rust substrate | ✅ default | 0.1.0-karmazyn-substrate · Z0 |
| Lua guest + host | ✅ | 1.1.x host · LUA monorepo |
| I/O × matryca T Stage 1 | ✅ | python + native tests |
| Studio SDL | ✅ MVP | mapa T tło, prompt full-window |
| **L1 Product host** | ✅ | `gate_product` + `dry_run_l1` · tag `l1-host-2026-07-31` |
| CI automatyczne | ✅ | `.github/workflows/gate.yml` |
| BootConfig / cmdline | ❌ | faza B (następna po L1) |
| GRUB / ISO (L2) | 📋 plan only | faza E — **nie done** |
| kentry Multiboot (L3) | 🚧 szkielet | `boot/kentry` — marker, nie Store |
| Store freestanding (L4) | 📋 plan only | faza G — **po** alloc design |

**Baseline gate (musi przechodzić przed nowymi fazami):**

```bash
# G0 — baseline
cd KarmazynOs
cargo test --manifest-path native/karmazyn_substrate/Cargo.toml
python test_substrate_compat.py -q          # gdy native zbudowany
python -m unittest software.test_io_thermal software.test_host_tools software.test_studio_sdl -q
python software/test_lua_release.py         # release gate Lua
python kernel_boundary.py kernel/ software/
```

| ID | Punkt sukcesu baseline |
|----|------------------------|
| **S0.1** | `cargo test` exit 0 |
| **S0.2** | `test_io_thermal` łącznie z `IoThermalNative` (gdy DLL/wheel jest) exit 0 |
| **S0.3** | boot native: log zawiera `I/O × matryca T — stage=1` (nie WARN/FAIL) |
| **S0.4** | `kernel_boundary` exit 0 |
| **S0.5** | `test_lua_release` / macierz tools bez regresji krytycznej |
| **SZ0.*** | Z0: prawo w crate Rust najpierw (ciągły warunek każdej fazy) |

---

## 3. Fazy budowy

### Faza A — **Utwardzenie Product host** (1–3 dni)

**Cel:** powtarzalny build native + boot na czystej maszynie Windows/Linux.

| Krok | Działanie | Artefakt |
|------|-----------|----------|
| A1 | Dokument install: rustup, MSVC **lub** MinGW, Python 3.10+, maturin, pygame | `Documents/install_product.md` |
| A2 | `build_native.ps1` / `.sh` idempotentny; błąd linkera = czytelny FAIL | skrypt |
| A3 | Jedna komenda `scripts/gate_product.(ps1\|sh)` = G0 | gate |
| A4 | Sync lustro root ← software tylko ze skryptu (albo usunąć lustra) | brak dryfu |
| A5 | `VERSION.txt` + data po każdym releasie substratu | wersja |

| ID | Punkt sukcesu A |
|----|-----------------|
| **SA.1** | Na czystym klonie: po `build_native` → `open_store(backend="native")` działa |
| **SA.2** | `gate_product` exit 0 na Windows (Twoja maszyna) i Linux (opcjonalnie CI) |
| **SA.3** | Brak rozjazdu `software/*.py` vs root dla boot/io (hash lub jeden path) |
| **SA.4** | Nowy dev: od zera do `python start.py --studio --check` ≤ 30 min z docem |

---

### Faza B — **BootConfig + cmdline** (2–4 dni)

**Cel:** jeden kontrakt konfiguracji (Stage 1 language: deterministyczny start).

| Krok | Działanie |
|------|-----------|
| B1 | `software/karmazyn_bootcfg.py` — `BootConfig` dataclass |
| B2 | Źródła (priorytet): defaults &lt; env &lt; argv &lt; (później cmdline GRUB) |
| B3 | Mapa: `substrate`, `guest`, `io`, `project`, `tick_ms`, `rescue`, `quiet` |
| B4 | `:info` pokazuje config + **source** każdej wartości |
| B5 | Testy golden stringów cmdline |

| ID | Punkt sukcesu B |
|----|-----------------|
| **SB.1** | `BootConfig` z unit testami ≥ 10 przypadków parsera |
| **SB.2** | `KARMAZYN_SUBSTRATE` / `--python` / env spójne z jednym obiektem |
| **SB.3** | Boot bez magii rozproszonej w 5 plikach (jedno `apply_boot_config`) |
| **SB.4** | `:info` zawiera linię `config: substrate=… source=env|default|argv` |

---

### Faza C — **Studio Product polish** (2–5 dni)

**Cel:** Studio SDL jako oficjalna powierzchnia operatorska (nie tylko demo).

| Krok | Działanie |
|------|-----------|
| C1 | Mapa T tło + prompt full-window (✅ zrobione) — utrzymać |
| C2 | `:hot` / status T w status barze na żywo z `thermal.stats` |
| C3 | Opcja `--fullscreen`, DPI, font size |
| C4 | Headless: tylko `--check`; GUI: dokument skrótów |
| C5 | Gate: studio check w `gate_product` |

| ID | Punkt sukcesu C |
|----|-----------------|
| **SC.1** | `karmazyn_studio.py --check` exit 0 na native i python |
| **SC.2** | Ręczny: Enter feed + hover heat widoczny na mapie tła (checklist 2 min) |
| **SC.3** | Anti self-heat: 60 s idle bez grow T_display do MAX (pomiar / asercja testowa) |
| **SC.4** | `Documents/studio_sdl.md` = aktualny layout (tło + prompt) |

---

### Faza D — **Release host 1.x** (1–2 dni)

**Cel:** tag / pakiet do użycia jako „Karmazyn runtime na hoście”.

| Krok | Działanie |
|------|-----------|
| D1 | Tag git np. `runtime-host-1.1.0` + `VERSION.txt` sync |
| D2 | Wheel native opcjonalny w CI lub instrukcja build |
| D3 | Checklist release (poniżej §5) podpisany |
| D4 | Krótki `CHANGELOG` PL |

| ID | Punkt sukcesu D |
|----|-----------------|
| **SD.1** | Tag w repo; `VERSION.txt` zgodny z tagiem |
| **SD.2** | G0 + studio check zielone na tagu |
| **SD.3** | Osoba B (lub Ty po 24 h na czystym env) odtwarza boot native bez ad-hoc fixów |
| **SD.4** | Znane limity spisane (brak bare-metal, host tools string-id na python) |

---

### Faza E — **Tor A: GRUB → Linux → Karmazyn** (1–2 tyg.)

**Cel:** pierwszy *wdrożeniowy* nośnik (ISO/VM), nie bare-metal.

| Krok | Działanie |
|------|-----------|
| E1 | Rootfs minimalny (Alpine/Debian slim lub Docker export) + native `.so` + monorepo |
| E2 | `boot/grub/grub.cfg` + cmdline → env/`BootConfig` |
| E3 | init → `karmazyn_boot` lub `karmazyn_studio` (framebuffer?) |
| E4 | `scripts/build_iso.sh` + QEMU smoke |
| E5 | Rescue entry: `substrate=python` |

| ID | Punkt sukcesu E |
|----|-----------------|
| **SE.1** | Artefakt `karmazyn.iso` (lub qcow) budowany jedną komendą |
| **SE.2** | QEMU: GRUB → login/init → sekwencja startowa z `stage=1` I/O (serial log) |
| **SE.3** | Cmdline `substrate=python` startuje rescue |
| **SE.4** | Czas od boot VM do promptu `karmazyn>` ≤ 60 s na typowym dev PC |
| **SE.5** | Dokument: `Documents/grub_howto.md` (build + run + fail cases) |

---

### Faza F — **Tor B: kentry Multiboot2** (równolegle / po E) (2–4 tyg.)

**Cel:** GRUB ładuje **własny** ELF; marker serial — bez pełnych usług.  
**Roadmapa:** `Documents/rust_roadmap_tech.md` · kod: `boot/kentry/`.

| Krok | Działanie | Stan |
|------|-----------|------|
| F1 | Crate `boot/kentry` Multiboot2 header | ✅ szkielet |
| F2 | Serial early print `KARMAZYN_KENTRY_OK` | ✅ w źródle + ELF (build `--target x86_64-unknown-none`) |
| F3 | Dump cmdline | ❌ |
| F4 | QEMU gate serial expect | ⏳ (manual / gdy ISO) |
| F5 | (później) link Store freestanding / alokator | ❌ po §4 roadmap |

| ID | Punkt sukcesu F |
|----|-----------------|
| **SF.1** | `cargo build` kentry exit 0 — ✅ (target none) |
| **SF.2** | QEMU + GRUB: serial zawiera `KARMAZYN_KENTRY_OK` — ⏳ |
| **SF.3** | Brak CPython w ścieżce kentry — ✅ |
| **SF.4** | Cmdline z Multiboot dostępne w kentry (string) — ❌ |

---

### Faza G — **Store po kentry** (4–8 tyg., strategiczne)

**Cel:** cold-boot bez Pythona: atom/tick/stats na serialu.

| ID | Punkt sukcesu G |
|----|-----------------|
| **SG.1** | Po kentry: create atom → tick → stats na serialu |
| **SG.2** | To samo prawo co `cargo test` substratu (podzbiór golden) |
| **SG.3** | I/O: SerialIo implementuje kontrakt `IoPort` (Stage 1 API) |
| **SG.4** | Python Store nadal golden; compat test nie regresuje |

---

## 4. Plan wdrożenia (operacyjny)

### 4.1 Środowiska

| Środowisko | Użycie | Substrat |
|------------|--------|----------|
| **Dev workstation** | rozwój, Studio | native default |
| **Gate local** | przed commitem | G0 |
| **VM/QEMU** | ISO / GRUB (faza E+) | native w rootfs |
| **Rescue** | awaria native | python + `KARMAZYN_IO_OPTIONAL` tylko świadomie |

### 4.2 Ścieżka wdrożenia host (fazy A–D)

```
1. rustup + toolchain (msvc|gnu)
2. git clone
3. .\native\build_native.ps1
4. .\scripts\gate_product.ps1     # lub równoważne
5. python start.py --studio       # operators
   lub python karmazyn_boot.py    # REPL
```

| ID | Punkt sukcesu wdrożenia host |
|----|------------------------------|
| **SW.1** | Kroki 1–4 bez ręcznej edycji PATH poza docem |
| **SW.2** | Gate exit 0 |
| **SW.3** | Studio lub REPL startuje; `:io` pokazuje stage=1 |

### 4.3 Ścieżka wdrożenia ISO (faza E)

```
1. build_native (Linux target)
2. pack rootfs + monorepo + grub
3. build_iso
4. qemu -cdrom karmazyn.iso -serial stdio
5. expect: BootLog stage=1 + prompt
```

| ID | Punkt sukcesu wdrożenia ISO |
|----|-----------------------------|
| **SI.1** | QEMU smoke automatyczny exit 0 |
| **SI.2** | Rollback: poprzedni ISO w artifacts/ |

### 4.4 Rollback

| Sytuacja | Akcja |
|----------|--------|
| Native broken | `KARMAZYN_SUBSTRATE=python` + issue; nie ciche WARN na Product bez flagi |
| ISO bad | boot poprzedniego ISO |
| Regresja Lua | tag `lua-v1.0.0` / gate release |

---

## 5. Macierz punktów sukcesu (scoreboard)

### Must (Product host — fazy A–D)

| ID | Opis | Mierzalne |
|----|------|-----------|
| **SZ0.1–SZ0.4** | **Rust pisze pod substrat od razu** | PR/review + cargo test first |
| S0.1–S0.5 | Baseline G0 | komendy exit 0 |
| SA.1–SA.2 | Build + gate na czysto | tak |
| SB.1–SB.3 | BootConfig | testy + jeden apply |
| SC.1 | Studio check | exit 0 |
| SD.1–SD.2 | Release tag + gate | tag + G0 |

### Should (wdrożenie dystrybucyjne)

| ID | Opis |
|----|------|
| SE.1–SE.2 | ISO + QEMU boot |
| SE.3 | Rescue cmdline |
| SF.1–SF.2 | kentry serial OK |

### Could (samowystarczalność głęboka)

| ID | Opis |
|----|------|
| SG.1–SG.3 | Store bez CPython po GRUB |
| Secure Boot / A-B | poza tym planem |

---

## 6. Definition of Done — „wdrożone” na poziomach

| Poziom | Nazwa | Warunek zbiorczy |
|--------|-------|------------------|
| **L0** | Lab OK | S0.* zielone na dev |
| **L1** | Product host | SA.* + SC.1 + SD.* — **tag release** |
| **L2** | Bootowalny obraz | SE.* — ISO w QEMU do promptu |
| **L3** | Własny loader payload | SF.* — kentry marker |
| **L4** | Samodzielny rdzeń | SG.* — Store po kentry bez Pythona |

**Rekomendacja kolejności wdrożeń:** L0 (teraz) → **L1 w pierwszej kolejności** → L2 → L3 → L4.

---

## 7. Ryzyka i progi stop

| Ryzyko | Próg stop | Mitygacja |
|--------|-----------|-----------|
| Native nie linkuje na Windows | SA.1 fail &gt; 1 dzień | toolchain gnu + doc; nie udawać Product |
| Dryf root/software | SA.3 | jeden path importu |
| Studio self-heat | SC.3 fail | note_visible tylko co N klatek (już) |
| ISO bez BootConfig | SE flaky | najpierw faza B |
| Tor B za wcześnie | brak L1 | nie zaczynać F przed D |

---

## 8. Harmonogram orientacyjny

| Tydzień | Faza | Cel sukcesu |
|---------|------|-------------|
| 0 (teraz) | — | L0: G0 zielone (baseline) |
| 1 | A + domknięcie C | SA.*, SC.1 |
| 1–2 | B | SB.* |
| 2 | D | **L1 release** SD.* |
| 3–4 | E | **L2** SE.* |
| 4–6 | F | **L3** SF.* |
| 6+ | G | L4 SG.* |

(Czasy elastyczne; L1 jest ważniejsze niż pośpiech do ISO.)

---

## 9. Checklist release L1 (do odhaczenia)

- [ ] **Z0:** brak semantyki GC/tick „tylko w Pythonie” od ostatniego tagu  
- [ ] `cargo test` + `build --release` native  
- [ ] `maturin` / wheel lub ctypes DLL na PATH  
- [ ] `unittest` io_thermal + host_tools + studio_sdl  
- [ ] `test_lua_release` / compat  
- [ ] `kernel_boundary`  
- [ ] boot native: `stage=1` w logu  
- [ ] `studio --check`  
- [ ] `VERSION.txt` + tag  
- [ ] `install_product.md` aktualny  
- [ ] Znane limity w CHANGELOG  

**Sukces L1 = wszystkie checkboxy + osoba odtwarza w ≤ 30 min.**

---

## 10. Jednozdaniowe cele sukcesu

| Poziom | Zdanie |
|--------|--------|
| **Z0** | „Każda zmiana prawa Store powstaje w crate Rust substratu; Python tylko lustrzy i testuje.” |
| **L1** | „Z klonu i rustup budujesz native i startujesz boot/studio z matrycą T stage=1 bez ręcznych hacków.” |
| **L2** | „Jedno ISO w QEMU dochodzi do `karmazyn>` z tym samym prawem Store.” |
| **L3** | „GRUB ładuje nasz ELF i pisze marker na serial.” |
| **L4** | „Po GRUB działa tick/GC bez CPythona — ten sam crate co Product.” |

---

*Aktualizować scoreboard przy domknięciu faz (data + commit/tag przy SA/SD/SE/SF/SG).*
