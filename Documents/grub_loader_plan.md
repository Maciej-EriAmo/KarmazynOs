# GRUB jako program ładujący KarmazynOs — lista i plan

**Status:** 📋 **PLAN TYLKO — NIE ZAIMPLEMENTOWANE** (L2/L3 w `build_deploy_plan.md`)  
**Nie mylić z L1 Product host** (boot na hoście Python/Rust DLL).  
**Data:** 2026-07-31  
**Powiązania:** `runtime_pl.md`, `ARCHITECTURE.pl.md`, `bubble_network_assumptions.md` §9, `native/README.md`, sekwencja `software/karmazyn_boot.py`

---

## 0. Cel

Ustalić **GRUB** (GNU GRUB / Multiboot) jako **program ładujący (stage-0/1)** w torze samowystarczalnego KarmazynOs:

```
firmware (UEFI/BIOS)
  → GRUB                          ← program ładujący (ten dokument)
  → karmazyn_kentry / obraz       ← entry jądra (substrat + init)
  → usługi                        ← gość, shell, scheduler, (HSS/HSL), …
```

**Zasada rozdziału (twarda):**

| Warstwa | Wolno | Nie wolno |
|---------|--------|-----------|
| **GRUB** | znaleźć nośnik, wybrać obraz, przekazać parametry, chainload | znać atomy, T, reach-GC, Lua, HRR |
| **Jądro** | Store, prawo T×reach, fasada, montaż szwów | zależeć od menu GRUB / składni `grub.cfg` |
| **Usługi** | gość, host API, lua_bin, shell, tick | startować przed gotowym Store |

Obecny `karmazyn_boot.py` **nie znika** — zostaje **stage-2 (userspace/init)** albo **dev-boot** na hoście Python, dopóki nie ma samodzielnego `kentry`.

---

## 1. Lista ról GRUB (co należy do loadera)

### 1.1 Obowiązki (MUST)

1. **Inicjalizacja platformy bootu** — UEFI lub BIOS legacy (przez GRUB).
2. **Wykrycie nośnika** — dysk / partycja / ISO / (opcjonalnie) sieć PXE.
3. **Wybór obrazu jądra** — ścieżka do ELF/PE Multiboot2 (lub Linux+initrd w torze pośrednim).
4. **Przekazanie cmdline** — klucze spójne z env runtime, np.:
   - `substrate=native|python` (dev)
   - `guest=lua|exec`
   - `quiet` / `verbose`
   - `root=` / `karmazyn_home=`
5. **Załadowanie + skok** do entry jądra (Multiboot2 preferred).
6. **Awaria czytelna** — brak obrazu / zły sum / timeout → komunikat GRUB, nie panic jądra.
7. **Opcja fallback** — drugi wpis menu: „Python reference / rescue”.

### 1.2 Zakazane w GRUB (MUST NOT)

1. Inicjalizacja Store / atomów / tick.
2. Montaż gościa Lua / `eval_line`.
3. Polityka HSS/HSL, pryzmaty, crypto sesji.
4. Logika reach-GC.
5. Zależność od `numpy` / Pythona w stage GRUB.

### 1.3 Opcjonalne (MAY)

1. Menu ratunkowe (rescue shell GRUB).
2. Chainload innego OS (dual-boot z hostem).
3. Weryfikacja podpisu obrazu (Secure Boot / GPG) — faza późna.
4. Serial console early.
5. Timeout + default entry (headless).

---

## 2. Mapowanie na obecną sekwencję bootu

Dzisiejszy raport usług w `boot()` mapuje się tak:

| Dziś (`karmazyn_boot`) | Po wprowadzeniu GRUB | Gdzie żyje |
|------------------------|----------------------|------------|
| proces hosta / `start.py` / Docker `bin/karmazyn` | **GRUB** ładuje obraz | firmware → GRUB |
| fasada jądra | init jądra po entry | `karmazyn_kernel` / `kentry` |
| HRR (opcjonalnie) | usługa / lib w jądrze | po Store |
| substrat Store (native default) | **rdzeń po skoku z GRUB** | Rust `native/` |
| warstwa wykonawcza (Lua) | usługa stage-2 | `LUA/` |
| narzędzia / projekt / host API / lua_bin | usługi | software |
| shell + scheduler | init / pid1-like w userspace runtime | `karmazyn_boot` lub następca |

**Skrót:** GRUB = *kto wstawia jądro w pamięć*; `karmazyn_boot` = *jak jądro budzi usługi*.

```
[ GRUB ]  ──load──►  [ kentry + Store ]  ──mount──►  [ gość + shell + tick ]
   ↑                        ↑                              ↑
 program ładujący      jądro (minimal)              kolejne usługi
```

---

## 3. Dwa tory (Dual-track) — wybór świadomy

### Tor A — **Hosted** (szybki, zgodny z dziś)

GRUB ładuje **Linux** (lub Windows nie — tu Linux/VM):

```
GRUB → vmlinuz + initrd → systemd/init → python|karmazyn → karmazyn_boot
```

- Cel: ISO/VM „Karmazyn jako środowisko”, bez pisania bare-metal.
- Kompilator jądra Karmazyn: **`rustc`** (native DLL/so) + Python runtime.
- GRUB: standardowy Linux path.

### Tor B — **Native Multiboot** (samowystarczalność Product)

GRUB ładuje **własny obraz Multiboot2**:

```
GRUB → karmazyn.elf (Multiboot2) → kentry → Store (Rust) → init usług
```

- Cel: Karmazyn jako *własny* ładunek, nie tylko app na Linuxie.
- Kompilator **konieczny:** `rustc` (+ `cargo`, target bare-metal lub freestanding).
- Linker Windows-host dev: MSVC/MinGW tylko do *build host*; target boot: `x86_64-unknown-none` / podobny.
- Python **nie** jest w ścieżce cold-boot Product (może zostać w torze A i w testach golden).

**Rekomendacja planu C:**  
**najpierw Tor A (ISO/VM + GRUB→Linux→Karmazyn)**, równolegle **kontrakt Multiboot i szkielet kentry (Tor B)** — bez udawania bare-metal przed stabilnym Store.

---

## 4. Lista artefaktów do zbudowania

| ID | Artefakt | Tor | Opis |
|----|----------|-----|------|
| G1 | `boot/grub/grub.cfg` | A+B | menu, cmdline, default, timeout |
| G2 | skrypt budujący ISO | A | `grub-mkrescue` / xorriso → `karmazyn.iso` |
| G3 | dokument cmdline | A+B | mapa flag GRUB ↔ env / kernel args |
| G4 | `kentry` (Rust) | B | entry Multiboot2, early log (serial/VGA) |
| G5 | linker script + Multiboot2 header | B | zgodność z GRUB |
| G6 | obraz `karmazyn.elf` / `.bin` | B | wynik `cargo build` freestanding |
| G7 | init stage-2 | A: `karmazyn_boot`; B: `kinit` | sekwencja usług jak dziś BootLog |
| G8 | rescue entry | A+B | fallback reference / shell GRUB |
| G9 | test QEMU | A+B | `qemu-system-x86_64 -cdrom …` smoke |
| G10 | CI gate | A+B | „ISO bootuje do promptu / do serial marker” |

---

## 5. Lista parametrów cmdline (kontrakt)

Wspólny zestaw (implementacja mapuje 1:1 w Tor A na env, w Tor B na tablicę args):

| Parametr | Domyślnie | Znaczenie |
|----------|-----------|-----------|
| `substrate=native` | native | Store Rust (Product) |
| `substrate=python` | — | tylko Tor A / rescue |
| `guest=lua` | lua | warstwa wykonawcza |
| `guest=exec` | — | mini-Lisp |
| `karmazyn_home=` | auto | root software / tools |
| `project=` | — | root projektu Lua |
| `verbose` | off | BootLog szczegółowy |
| `quiet` | off | mniej logów |
| `tick_ms=` | 2000 | scheduler (gdy usługa wstanie) |
| `rescue` | off | pomiń usługi niekrytyczne |

**Zasada:** GRUB *tylko przekazuje string*; parsowanie w `kentry` / `karmazyn_boot`.

---

## 5b. Żeby to wypaliło — elementy poza samym GRUB

GRUB bez domkniętych szwów poniżej to tylko menu.  
**Product boot = GRUB + cmdline + I/O + pamięć/czas + init usług.**

### Mapa zależności (minimalny łańcuch)

```
firmware
  → GRUB (ładuje obraz + surowy cmdline)
  → kentry / Linux init
       ├─ [CL]  parser linii komend → BootConfig
       ├─ [IO]  konsola / serial / stdin-stdout abstraction
       ├─ [MEM] mapa pamięci (Multiboot / OS) + heap
       ├─ [TIME] zegar / tick source
       ├─ [LOG] early log (ten sam kanał co BootLog)
       └─ [FS?] root / karmazyn_home (Tor A: VFS hosta; Tor B: później)
  → Store (substrat)
  → gość + host API (używa [IO])
  → shell (używa [CL meta :] + [IO])
  → scheduler (używa [TIME] + Store.lock)
```

---

### A. Linia komend (cmdline) — pełny kontrakt

Dziś: `sys.argv` + env (`KARMAZYN_*`) w `karmazyn_boot` / `start.py` — **rozproszone**.  
Potrzeba: **jedna struktura `BootConfig`**, zasilana z trzech źródeł w tej kolejności:

| Priorytet | Źródło | Kiedy |
|-----------|--------|--------|
| 1 (najniższy) | defaults w kodzie | zawsze |
| 2 | plik / identity (opcjonalnie) | Tor A / później |
| 3 | **cmdline GRUB / Multiboot** | cold boot |
| 4 | env (`KARMAZYN_*`) | Tor A, dev, Docker |
| 5 (najwyższy) | `argv` procesu (`--lua`, `--project`, …) | dev / test |

**Artefakty do zrobienia:**

| ID | Element | Stan dziś | Cel |
|----|---------|-----------|-----|
| CL1 | `BootConfig` (dataclass / dict kanoniczny) | brak | jeden typ: substrate, guest, paths, tick_ms, quiet, rescue, io=… |
| CL2 | parser stringu cmdline | częściowy (flagi CLI) | `key=val` + flagi bool, cytowanie, ignoruj nieznane z WARN |
| CL3 | mapa cmdline ↔ env | ad hoc | dokument + funkcja `apply_boot_config(cfg)` → env + obiekt |
| CL4 | dump `:info` / early log | `kernel_info` | pokazać skąd wzięto wartości (`source=cmdline|env|default`) |
| CL5 | walidacja | słaba | złe `substrate=` → FAIL stage1, nie ciche python |
| CL6 | testy jednostkowe parsera | brak | golden strings z `grub.cfg` |

**Rozszerzenie parametrów (obok §5):**

| Parametr | Znaczenie I/O / systemu |
|----------|-------------------------|
| `console=serial\|vga\|stdio\|null` | kanał konsoli operatorskiej |
| `serial=0x3f8\|…` | port COM (Tor B / QEMU) |
| `log=early\|full` | poziom BootLog |
| `io=host\|queue\|null` | backend I/O gościa (patrz B) |
| `nosleep=1` | bez sleep w tools (już częściowo `KARMAZYN_NOSLEEP`) |
| `identity=` | ścieżka identity.bin / sesja Φ (później) |

**Reguła:** shell meta (`:guest`, `:project`) **mutuje runtime**, ale nie przepisuje historii cmdline; cold-boot zawsze odtwarzalny z tego samego stringa GRUB.

---

### B. Interfejsy I/O — warstwa, której dziś prawie nie ma jako HAL

Dziś I/O jest **przyklejone do hosta CPython**:

| Ścieżka | Implementacja dziś | Problem pod GRUB/kentry |
|---------|-------------------|-------------------------|
| REPL | `input()` / `print()` | brak w bare-metal |
| historia | `readline` | opcjonalna, host-only |
| gość `print` | stdout procesu | brak abstrakcji |
| `karmazyn.read_line` | kolejka `_io_input` **lub** stdin | częściowy szew — dobry kierunek |
| `clear_screen` | ANSI na TTY | wymaga konsoli znakowej |
| demo / testy | wstrzyknięte `io_input` | model do **kanonizacji**, nie wyjątek |

**Docelowy kontrakt `IoPort` (minimalny HAL):**

```text
IoPort
  write(bytes|str) -> None      # stdout / serial TX
  write_err(bytes|str) -> None  # diagnostyka (może = write)
  read_line(prompt?) -> str     # blokująco lub z kolejki
  try_read() -> Optional[str]   # nieblokująco (scheduler-friendly)
  is_tty() -> bool
  clear() -> None               # opcjonalnie no-op
```

**Backendy:**

| Backend | Tor | Użycie |
|---------|-----|--------|
| `StdioIo` | A, dev | stdin/stdout procesu (dziś) |
| `QueueIo` | A+B testy | `io_input` — smoke lua_bin bez klawiatury |
| `SerialIo` | B, QEMU | early + REPL na COM1 |
| `VgaTextIo` | B opcjonalnie | 80×25, później |
| `NullIo` | headless CI | tylko log do bufora pamięci |
| `CompositeIo` | Product | serial + stdio mirror |

**Artefakty:**

| ID | Element | Cel |
|----|---------|-----|
| IO1 | trait/protokół `IoPort` | jedna powierzchnia dla boot, shell, host, gość |
| IO2 | `StdioIo` + `QueueIo` | zero regresji dev/test |
| IO3 | podpięcie `KarmazynShell` do `IoPort` (nie goły `input`) | ten sam kod w QEMU i na PC |
| IO4 | `install_karmazyn_host(..., io=port)` | `read_line` / print path przez port |
| IO5 | early log kentry → ten sam port | BootLog stage0/1 na serial |
| IO6 | polityka buforowania | linia vs znak; UTF-8 MVP (ASCII first w B) |
| IO7 | rozdział **konsola operatorska** vs **I/O gościa** | gość nie psuje logów jądra (2 kanały lub tagi) |

**Kolejność montażu I/O (twarda):**

1. Early: najprostszy port (serial lub null) — zanim Store  
2. Po cmdline: wybór `console=` / `io=`  
3. Po Store: shell + host dostają ten sam (lub złożony) port  
4. Gość: tylko przez host API / `print` zhookowany do portu, **nie** surowy hardware  

---

### C. Pozostałe elementy (checklista „wypali”)

Bez tych punktów cold-boot padnie mimo GRUB + cmdline + I/O:

| ID | Element | Po co | Tor | Priorytet |
|----|---------|-------|-----|-----------|
| MEM1 | Mapa pamięci | heap Store / alokacje | B | P0 dla B |
| MEM2 | Allocator (bump → lepszy) | atomy/bąble | B | P0 dla B |
| TIME1 | Źródło czasu | `tick`, decay, scheduler, uptime | A: host clock; B: PIT/HPET/TSC | P0 |
| TIME2 | `tick_ms` z cmdline | spójność z schedulerem | A+B | P1 |
| LOCK1 | `Store.lock` / single-thread reguła | scheduler vs REPL | A jest; B: jawny model | P0 |
| LOG1 | Early + late logging | ten sam format `[ OK ]` | A+B | P0 |
| PANIC1 | Panic/halt path | czytelny na serial, bez traceback Py | A+B | P0 |
| FS1 | Root / `karmazyn_home` | LUA, lua_bin, tools | A: VFS hosta | P0 Tor A |
| FS2 | Projekt host→bąbel | `:project` / require | A; B później | P1 |
| ID1 | Identity / sesja Φ | HSL, persystencja | później | P2 |
| CAPS1 | Capabilities gościa | sandbox (już szkic `caps=` w mount) | A+B | P1 |
| EVT1 | EventBus vacuum_decay | diagnostyka, verbose | A jest | P2 |
| NET0 | L0 / sieć | poza minimum bootu | — | P3 |
| HSS0 | HSS/HSL daemony | po shell | — | P3 |
| SEC1 | Secure Boot / podpis | F5 | — | P3 |

---

### D. Szwy istniejące do **kanonizacji** (nie wymyślać od zera)

| Szw | Już jest | Co domknąć |
|-----|----------|------------|
| Montaż gościa | `eval_line` + `.env` Bubble | bez zmian kontraktu |
| CLI gość/projekt | `--lua`, `--project`, env | scalić w `BootConfig` |
| Host I/O | `_io_input`, `read_line`, `clear_screen` | wyciągnąć za `IoPort` |
| Boot raport | `BootLog` | dodać stage + źródło config + backend I/O |
| Substrat | `open_store` / native default | cmdline `substrate=` → backend |
| Granica jądra | `kernel_boundary` | I/O HAL **nie** w `kernel/` jeśli to software — albo cienki `kio` w kentry |

**Propozycja podziału modułów:**

```
software/karmazyn_bootcfg.py   # CL1–CL3 BootConfig + parser
software/karmazyn_io.py        # IoPort + Stdio/Queue/Null
software/karmazyn_boot.py      # używa cfg + io (nie implementuje ich w środku)
boot/kentry/                   # early SerialIo + parse Multiboot cmdline
```

---

### E. Definition of Done — „wypaliło” na poziomie szwów

| Poziom | Warunek |
|--------|---------|
| **S0** | `BootConfig` z argv/env; testy parsera |
| **S1** | Shell + host na `IoPort` (stdio); demo/testy na `QueueIo` bez regresji |
| **S2** | Cmdline string z §5 w pełni mapowany; `:info` pokazuje config |
| **S3** | Tor A ISO: GRUB cmdline → ten sam `BootConfig` → prompt na konsoli VM |
| **S4** | Tor B: serial IoPort + marker + (później) Store log na tym porcie |

**Wniosek operatorski:**  
Faza 0/1 loadera **musi** iść w parze z **S0–S2** (cmdline + I/O).  
Bez tego ISO z GRUB i tak nie da kontrolowanego Product bootu.

---

### F. Kolejność prac (wpleść w fazy §6)

| Kiedy | Co |
|-------|-----|
| **Przed / z Fazą 0** | CL1–CL3, IO1–IO3 (userspace) |
| **Z Fazą 1 (ISO)** | CL cmdline z grub.cfg → BootConfig; console=stdio; FS1 rootfs |
| **Z Fazą 2 (kentry)** | IO5 SerialIo early; CL z Multiboot info |
| **Z Fazą 3 (Store)** | MEM*, TIME1, LOCK1, LOG na serial |
| **Z Fazą 4 (usługi)** | IO4 host, CAPS1, shell na IoPort |
| **Później** | ID1, NET0, HSS0, SEC1 |

---

## 6. Plan fazowy


### Faza 0 — Uporządkowanie loadera w userspace (1–2 dni)

**Cel:** obecny boot wygląda i raportuje jak „grub stages”, bez prawdziwego GRUB.

- [ ] Wydzielić w `karmazyn_boot` (lub cienkim `karmazyn_loader.py`) etapy nazwane:
  - `stage0` — proces/host (odpowiednik firmware)
  - `stage1` — fasada + Store (odpowiednik jądra)
  - `stage2` — gość + shell + scheduler (usługi)
- [ ] Utrzymać istniejący `BootLog` `[ OK ]/[WARN]/[FAIL]`
- [ ] Spisać mapowanie stage ↔ GRUB (ten dokument §2)
- [ ] Gate: `python karmazyn_boot.py --demo` bez regresji

**Wynik:** słownik i szwy gotowe pod prawdziwy GRUB; zero regresji Product.

---

### Faza 1 — Tor A: GRUB → Linux → Karmazyn (ISO/VM) (3–7 dni)

**Cel:** pierwszy *prawdziwy* GRUB ładuje system z Karmazyn jako payload.

- [ ] Katalog `boot/grub/grub.cfg` + wpisy: *Karmazyn (native)*, *Karmazyn (python rescue)*
- [ ] Minimalny rootfs / Docker-export / Alpine-like z:
  - Python 3.10+
  - `native` so/dll (Linux: `.so`)
  - `kernel/` + `software/` + `LUA/` + `lua_bin/`
- [ ] init: `exec karmazyn_boot` (jak `bin/karmazyn`)
- [ ] Budowa ISO (`grub-mkrescue` lub równoważne)
- [ ] Smoke QEMU: do promptu `karmazyn>` lub markera demo
- [ ] Dokument: `Documents/grub_howto.md` (build + run)

**Kompilator:** `rustc` (target host Linux `x86_64-unknown-linux-gnu`) do substratu; **nie** bare-metal.

**Gate:** `qemu … -cdrom karmazyn.iso` → sekwencja startowa OK.

---

### Faza 2 — Kontrakt Multiboot2 + szkielet `kentry` (Tor B, szkielet) (1–2 tyg.)

**Cel:** GRUB *potrafi* załadować własny ELF; jeszcze bez pełnych usług.

- [ ] Crate `native/karmazyn_kentry` (lub `boot/kentry`):
  - Multiboot2 header
  - early serial print: `KARMAZYN_KENTRY_OK`
  - halt lub nieskończona pętla ze statusem
- [ ] `grub.cfg` entry wskazujący na ten ELF
- [ ] QEMU: GRUB menu → kentry marker na serial
- [ ] Cmdline dump (surowy string z multiboot info)

**Kompilator:** `rustc` + target freestanding (`x86_64-unknown-none` lub custom).  
**Nie** wciągać Store do kentry w tej fazie (minimalny entry only).

**Gate:** serial zawiera `KARMAZYN_KENTRY_OK` po wyborze wpisu.

---

### Faza 3 — Jądro minimalne po kentry (Tor B, rdzeń) (2–4 tyg.)

**Cel:** po GRUB wstaje **Store reach-GC** bez Pythona.

- [ ] Przenieść / podlinkować prawo substratu (atoms, bubbles, roots, tick) do freestanding lub `no_std`+allocator
- [ ] Early heap / bump allocator (MVP)
- [ ] Testy golden: subset `test_substrate` przeniesiony na host-unit + QEMU smoke
- [ ] Brak gościa Lua w tej fazie (albo minimalny `eval` stub)
- [ ] Log analogiczny do BootLog na serial

**Ryzyko główne:** `no_std` + GC + FFI — trzymać MVP ciasno (prawo T×reach, bez HRR).

**Gate:** w QEMU: create atom → tick → stats po serialu.

---

### Faza 4 — Usługi stage-2 na native path (3–6 tyg.)

**Cel:** po jądrze montują się **kolejne usługi** jak w kanonie.

Kolejność montażu (ta sama co dziś, twarda):

1. fasada / API jądra  
2. Store (już żywy z F3)  
3. warstwa wykonawcza (Lua guest — port lub host-side najpierw)  
4. host API / tools  
5. shell  
6. scheduler termiczny  
7. (opcjonalnie) HSS/HSL, L0  

- [ ] Decyzja: Lua **in-process** (port) vs **osobny proces** na microkernel-like  
  - *MVP rekomendacja:* najpierw interpreter minimalny lub odłożony gość; nie blokować Store  
- [ ] Rescue path bez Lua  
- [ ] Zgodność kontraktu `eval_line` + `.env` Bubble  

**Gate:** interakcja minimalna (nawet bez pełnej Lua 1.0) + `:stats`/serial stats.

---

### Faza 5 — Utwardzenie Product (ciągłe)

- [ ] Secure Boot / podpis obrazu (opcjonalnie)
- [ ] A/B sloty lub wersjonowanie obrazu
- [ ] Telemetria startu (czasy stage jak BootLog ms)
- [ ] CI: QEMU + serial expect
- [ ] Dokument operatorski + recovery

---

## 7. Lista zadań (backlog spłaszczony)

**P0 — teraz (bez bare-metal)**

1. Zaakceptować ten dokument jako kanon loadera.  
2. Faza 0: nazwane stage w boot logu.  
3. **`BootConfig` + parser cmdline/env/argv** (CL1–CL3) — bez tego GRUB nie ma co przekazać.  
4. **`IoPort` + StdioIo/QueueIo; shell/host na porcie** (IO1–IO4) — bez tego brak konsoli po starcie.  
5. Szablon `grub.cfg` (nawet bez ISO).  
6. Utrzymać native default (`rustc`) jako warunek Product Store.

**P1 — pierwszy prawdziwy GRUB**

5. Tor A ISO + QEMU.  
6. Cmdline → env map.  
7. Rescue entry (python substrate).

**P2 — własny payload**

8. Multiboot2 `kentry`.  
9. Serial marker smoke.  
10. Store freestanding MVP.

**P3 — usługi**

11. Kolejność usług jak BootLog.  
12. Gość + shell.  
13. Scheduler.  
14. HSS/HSL poza minimum.

---

## 8. Kryteria akceptacji (Definition of Done)

| Poziom | Warunek |
|--------|---------|
| **L0 Loader vocab** | Stage nazwane; dokument zsynchronizowany z `runtime_pl.md` |
| **L1 GRUB hosted** | ISO/QEMU: GRUB menu → Karmazyn prompt (Tor A) |
| **L2 GRUB native entry** | GRUB → ELF → `KARMAZYN_KENTRY_OK` (Tor B) |
| **L3 Kernel after GRUB** | Store tick/stats bez Pythona w ścieżce cold-boot |
| **L4 Services** | gość + shell + scheduler po kentry |

Samowystarczalność Product w sensie loadera = **co najmniej L1**, cel strategiczny **L3+**.

---

## 9. Zależności narzędziowe

| Narzędzie | Po co | Faza |
|-----------|--------|------|
| **`rustc` / cargo** | substrat native + kentry | zawsze Product; B od F2 |
| GRUB 2 (`grub-mkrescue`, modules) | ISO / boot | F1+ |
| xorriso / mtools | budowa ISO | F1 |
| QEMU | smoke | F1+ |
| Python 3.10+ | Tor A, golden tests, dev-boot | F0–F1; nie cold-boot B |
| MSVC **lub** MinGW | link host Windows przy build native | dev host |
| (opc.) Docker | rootfs Tor A | F1 |

**Kompilator konieczny w torze loadera Product:** `rustc`.  
GRUB sam w sobie nie zastępuje kompilatora jądra — tylko **ładuje** wynik.

---

## 10. Ryzyka i świadome uniki

| Ryzyko | Mitygacja |
|--------|-----------|
| Próba bare-metal zanim Store jest stabilny | Tor A najpierw; F2 tylko marker |
| GRUB „zna się” na Φ/T | twardy MUST NOT §1.2 |
| Python ukryty w cold-boot B | gate L3: brak CPython w ścieżce |
| Rozjazd cmdline / env | jeden dokument mapy §5 + test |
| Lua blokuje kentry | gość dopiero F4 |
| Secure Boot za wcześnie | F5 |

---

## 11. Propozycja layoutu repo (gdy ruszy implementacja)

```
KarmazynOs/
  boot/
    grub/
      grub.cfg                 # G1
    kentry/                    # F2+ (Rust Multiboot2)
      Cargo.toml
      src/main.rs
    README.md
  Documents/
    grub_loader_plan.md        # ten plik
    grub_howto.md              # F1 (build/run)
  software/karmazyn_boot.py    # stage-2 / Tor A init
  native/karmazyn_substrate/   # prawo Store
```

---

## 12. Następny konkretny krok (jedna sesja)

1. **`BootConfig` + parser** (argv/env → jeden obiekt; testy na stringach z grub.cfg).  
2. **`IoPort`**: wyciągnąć `input`/`print`/`_io_input` za `StdioIo` + `QueueIo`; shell i host przez port.  
3. BootLog: stage + `io=` + źródło config.  
4. Szablon `boot/grub/grub.cfg` z cmdline z §5.  
5. Bare-metal dopiero po S1–S2 albo świadomym Tor B.

---

## 13. Jednozdaniowe podsumowanie

> **GRUB ładuje obraz i podaje string; `BootConfig` go interpretuje; `IoPort` daje konsolę; jądro budzi Store; init montuje usługi — bez cmdline i I/O loader nie „wypala”.**

*Dokument żywy — aktualizować przy domknięciu faz (checkboxy + data gate).*
