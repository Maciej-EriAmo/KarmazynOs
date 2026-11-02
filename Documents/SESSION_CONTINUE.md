# SESSION_CONTINUE — KarmazynOs (kontynuacja)

**Data:** 2026-11-02  
**Repo Os:** `main` @ **`4b62776`** (+ commit z tym plikiem), bez push  
**DBase:** `master` @ **`39f696e`**, zsynchronizowany z originem  
**Kanon:** [`KANON.md`](KANON.md) — jądro Linuksa jest nośnikiem (proces, sterowniki). System plików to bąble i atomy w KAFD. Sieć to Cynober-Secure/HSL do Karmin_DB.

**Zasada konstrukcji (2026-11-02):** tylko jądro jest z Linuksa. Element systemu jest bąblem i atomami w Store, a jego życiem rządzi T×reach. Plik, katalog, proces potomny, sygnał, kod wyjścia, ścieżka XDG to szczegóły nośnika — nie model i nie to, co widać w UI. Budowa zgodna z Linuksem jest błędem konstrukcyjnym. Przemianowanie nie jest naprawą.

**Słownik:** to, co w Linuksie byłoby demonem albo usługą, to **servitor** (polecenie `servitor`, korzeń `servitory`).

---

## Stan płyty `out/karmazyn-linux.iso` (`scripts/build_linux_shell.ps1`)

| Obszar | Stan |
|--------|------|
| Konsola | ekran VGA (tty1) + serial (ttyS0) naraz, `KARMAZYN_CONSOLE=auto\|vga\|serial\|none`; na tty1 font `Lat2-Terminus16` (kbd-misc 2.8.0, GPL-2.0+, `/font` w initramfs, `KARMAZYN_FONT`) z polskimi literami |
| Trwałość | Store = świat DBase `karmazyn_store_v1.4_kafx`: KAFD w kopercie KAFX w `/data/cynober/worlds/karmazyn.kafd` na ext4 (`/dev/vda` → `/data`); pusty dysk dostaje sam ext3 z dziennikiem JBD2 (`ext2.rs`, rozmiar jak `mke2fs`; po twardym wyłączeniu `recovery complete`, bez `mounting unchecked fs`), inny tylko `disk format`; świat nieczytelny = zapis wstrzymany; autosync po zmianie treści, przyrostowo: zmiany do `karmazyn.kafs` (ramki KAFS w KX1), `sync` i próg = pełna migawka `.kafd` i pusty dziennik (`WorldLog` w `karmazyn_kafd`); po zapisie `syncfs` (chroni też dyski ext2 sprzed dziennika) |
| KAFD natywnie | `native/karmazyn_kafd`: v2.0/v2.1/KTIX/v1-odczyt, KAFS, dziennik, compact, KAFX/KX1, świat DBase (`world`, cecha `substrate`) — bajt w bajt z Pythonem |
| Sieć | `KARMAZYN_IP` / `KARMAZYN_GW` (grub.cfg: QEMU, host = 10.0.2.2), virtio_net; `KARM_PSK` i `KARM_HSS_PROFILE` z aktywnego profilu w `/data/cynober/client.json` (obok `master.key`); brak pliku = ECDH |
| Karmin_DB | `native/karmazyn_cynober` (ECDH, HSS standard/production, HSL-1.1, PSK, QKD); w shellu `db connect / db <KarminQL> / db info / db close` |
| Narzędzia | bąbel kodu: etykieta = nazwa, źródło w atomie `src` (E=`lua`), bąbel jest korzeniem. `tool <etykieta>`, `require` po `code.link` albo w górę rodziców, `nano`/`edit` na źródle. `lua_bin/` jest ziarnem wchłanianym przez PID 1 |
| Epoki | PID 1 ma zegar epok: `KARMAZYN_TICK_MS=2000` w `grub.cfg` (0 = tylko `tick`/`settle`; na hoście domyślnie wyłączony). Epoka = tick Store + epoka sesji Lua + krok servitorów. Wejście czyta wątek, jedna linia na żądanie (`edit`, `nano` mają klawiaturę dla siebie). Linia startowa `epoki — co 2000 ms` |
| Servitory | bąbel kodu w gościu Lua, nie proces. `servitor up <etykieta>` wiąże `src` z korzeniem `servitory` (reach = czy) i daje T_INIT; `servitor down` odpina. Krok w epoce, gdy `src` HOT/WARM (T = kiedy). Chunk zwraca `true` = pracował (grzeje), nic = bezczynny (stygnie, zasypia), `false` = skończył (poza zasięgiem); błąd nie grzeje. `karmazyn.code.wake(etykieta)` budzi przez T. Krok nie czyta klawiatury |
| Dziennik | `dziennik [n]`: wpisy startu, poleceń i servitorów to atomy (E=`dziennik`) w korzeniu `dziennik`; ponad 200 odpięte i zbierane przez vacuum; nie budzą autosync, na dysk idą z najbliższym zapisem świata. Tylko PID 1 i tryb interaktywny (batch na hoście liczy id od zera) |
| Czas | `czas`: stempel jako atom `stempel` w korzeniu `czas`, w świecie KAFD; cofnięty zegar = ostrzeżenie; opcjonalne SNTP przez `KARMAZYN_NTP=host[:port]` (odrzuca kiss-o'-death). Drugi rozruch zapisuje dysk raz: nowy stempel |

## Bramki / testy

```powershell
cd C:\Users\drwis\KarmazynOs
.\scripts\build_linux_shell.ps1          # płyta (toolchain GNU wybiera sam)
.\boot\linux\qemu_serial.ps1             # shell, Lisp, Lua, limit instrukcji
.\boot\linux\qemu_disk.ps1               # ext4 + świat KAFX przez restart; servitor, dziennik, stempel, zegar epok
.\boot\linux\qemu_vga.ps1                # ekran + serial, zrzut out\karmazyn-vga.png
.\boot\linux\qemu_net.ps1                # sieć + db do żywego cynober_server.py
.\native\stage2_verify.ps1               # bramka shella (bąble po @etykiecie)
python native\karmazyn_kafd\cross\cross_check.py      # KAFD/KAFX/świat vs DBase
python native\karmazyn_cynober\cross\live_check.py    # klient vs żywy serwer DBase
```

Skrypty `.ps1` uruchamiać z PowerShella, nie przez `pwsh` z Git Basha (tam `link` z coreutils psuje wybór toolchainu). Ostatni przebieg 2026-11-02: `qemu_serial`, `qemu_disk`, `stage2_verify` zielone; `qemu_vga` i `qemu_net` w tej sesji nie były puszczane.

---

## Domknięte w tej sesji (2026-11-02)

1. **Servitory, dziennik i stempel czasu z prawa substratu.** Pierwsza wersja (katalogi usług à la runit/s6 z plikami `run`/`down`/`needs`, procesy potomne i sygnały, plik dziennika z rotacją, `clock.stamp` w `$HOME/.local/share`) była konstrukcją Linuksa — cofnięta trzema revertami (`a84e3a0`, `3b55d54`, `449d9f8`) i zbudowana od nowa (`841c913`, nazwa `f814194`). Bramki: `qemu_disk.ps1` (przetrwanie restartu), `stage2_verify.ps1`.
2. **Zegar epok PID 1 i grzanie tylko pracą** (`4b62776`). Krok na każde zdarzenie odrzucony: omijałby T = kiedy. Zdarzenie działa przez T (`code.wake`).
3. **Dysk: `syncfs` po zapisie świata** (`3e2b8af`). Po twardym wyłączeniu następny zapis trafiał na i-węzeł zajęty („doubly allocated”, potem I/O error i ENOSPC). Ujawniło się, gdy drugi rozruch zaczął pisać stempel.
4. **Jednorodne nazewnictwo.** `servitor` w shellu, `tools_lua.md` i `grub_loader_plan.md` (`cf50ddf`). HSS w mapie, `ARCHITECTURE*`, `README` to servitor w gościu, nie demon (`6005371`).

Szczegół poleceń: [tools_lua.md](tools_lua.md). HSS: [linux_hss_roadmap.md](linux_hss_roadmap.md), faza 3.

## Do zrobienia w następnej sesji

1. ~~Dziennik ext4 na dysku.~~ **Zrobione 2026-11-02:** formater zakłada dziennik JBD2 (i-węzeł 8). `qemu_disk.ps1` sprawdza `with ordered data mode` i brak `mounting unchecked fs` po twardym wyłączeniu. CI (`gate.yml`): krok kentry padał od 2026-10-29, bo cargo czyta `.cargo/config.toml` z katalogu wywołania — poprawione (`8c49e6d`); run `41423204289` na `d400fed` zielony, pierwszy od tamtej pory.
2. ~~Przyrostowy zapis KAFS.~~ **Zrobione 2026-11-02:** `WorldLog` (`karmazyn_kafd`, cecha `substrate`): autosync dopisuje zmienione dokumenty do `karmazyn.kafs`, bez T (stygnięcie nie przepisuje dokumentów), usunięte jako puste ramki, liczniki ramką `@native`. Compact = pełny `write_world`, czyli migawka jak z Pythona; świat z obcymi id dostaje pełny zapis przy pierwszej zmianie. Bramki: testy `worldlog_*` (jeden atom = jedna ramka, koperta bajt w bajt ta sama), `cross_check.py` (Python czyta dziennik i migawkę po compact), `qemu_disk.ps1` (zapis po `sync` żyje tylko w dzienniku i przechodzi restart). Python sam nie czyta `.kafs` świata: widzi stan z ostatniej migawki.
3. ~~Polskie znaki na VGA.~~ **Zrobione 2026-11-02:** PID 1 wczytuje `Lat2-Terminus16` na `/dev/tty1` (`KDFONTOP` + `PIO_UNIMAP`, parser PSF2 w `console.rs`); font z `kbd-misc-2.8.0-r0.apk` (suma SHA-256 w `build_linux_shell.ps1`). `qemu_vga.ps1` sprawdza linię `tty1 (Lat2-Terminus16)` i pangram z serialu; zrzut pokazuje ąćęłńóśźż i wielkie litery.
4. **Dwa braki klienta Cynober** (po dysku, bo zmieniają kontrakt na drucie). W `native/karmazyn_cynober`: profil HSS `proto` (macierz z PCG64, jak NumPy w DBase) i ramki KAFS (media put/get). Dziś `proto` spada do ECDH, a ramka KAFS jest odrzucana. Bramka: `live_check.py` przeciw żywemu `cynober_server.py`, w tym `proto` i jeden media put/get.

## Do decyzji (przed fazą 3 HSS)

- **Długość epoki płyty.** Decyzja HSS przychodzi najpóźniej po jednej epoce; 2000 ms to za wolno dla dostępu do pliku. Krótsza epoka przyspiesza też stygnięcie całego świata (przy 200 ms osierocony atom znika po kilku sekundach zamiast ~80 s). Alternatywa: dłuższy limit czasu w module HSL.
- **API hosta dla servitora HSS:** HMAC na kluczu z keyringu PID (bez bajtów klucza w gościu), odczyt pytania, zapis odpowiedzi. Kanał `/dev/hss` → PID 1 → atom pytania w bąblu `hss` → `code.wake('hss')`.

## Na prośbę, poza tą kolejką

- Servitor HSS (upcall HSL), faza 3 `linux_hss_roadmap.md` — bąbel kodu w gościu, nie demon; zegar epok już jest, reszta w „Do decyzji”.
- DBase: czerwony test `tests.test_kernel TestStore.test_nested_tick_is_noop` (był wcześniej). Wzmianka o natywnym KAFD w `DBase/docs/KAFD.md`.
- DHCP i klawiatura USB na prawdziwym sprzęcie. Moduły `virt` pod to nie były sprawdzane.
- `rustc` na płycie, samobudowa ISO, własne jądro, faza G Store bez nośnika.
- Dopieszczanie gościa Lua 1.1.3 (`puc_subset`) — to host, nie ta płyta.
- `generate_from_idea` zostaje `nil`. `ThermalSurface.write(..., visible=True)` nie grzeje macierzy.
- `Documents/grub_loader_plan.md` ma domyślne `tick_ms=2000` — zgodne z płytą; przy zmianie długości epoki poprawić oba miejsca.

---

# Sesja 2026-10-30 — archiwum

**Repo Os:** `main` @ `546cf72`. **DBase:** `39f696e` (potem wypchnięty).

1. **Narzędzia są bąblami substratu.** Kod = bąbel-korzeń o etykiecie plus atom `src`. `tool` woła bąbel, `require` idzie po powiązaniu albo w górę rodziców. Ziarno `lua_bin` wchodzi do świata tylko jako PID 1, po wczytaniu świata, i tylko dla etykiet bez `src`. Stare pliki `bin/` i `lib/` w `karmazyn.fs` zostają dokumentami.
2. **Sekrety sieci są w pliku.** `KARM_PSK` i `KARM_HSS_PROFILE` z aktywnego profilu w `/data/cynober/client.json` (obok `master.key`). Brak pliku zostawia ECDH. Środowisko ma pierwszeństwo przed plikiem.

---

# Sesja 2026-08-07 — archiwum

## SESSION_CONTINUE z 2026-08-07

**Data:** 2026-08-07 (koniec sesji)  
**Repo Os:** `main` @ ok. **`5741598`** (+ KANON/SEAL/shell/lifecycle w historii)  
**DBase:** backend STRICT zsynchronizowany (`033914b`)  
**Holon:** `C:\Users\drwis\Karmin_Ae` → `python agent_boot.py --project Karmazyn`  
**Kanon:** [`KANON.md`](KANON.md) · uszczelnienie: [`SUBSTRATE_SEAL.md`](SUBSTRATE_SEAL.md)

---

## Model (nie gubić)

| | |
|--|--|
| **Król** | tylko **substrat** (A/B/T/reach) |
| **Minister** | DB, Holon, Studio, shell, języki — przez **szwy** |
| **Rust** | kości + wykonanie silnika |
| **Userspace** | klient; nie włada A/B (są niżej) |
| **Shell / ksub** | operator sys, nie wzorzec product |
| **Atom** | `(S, E, T)` — **S = sygnatura** |
| **Zamrożenie** | projekcja poza Store (nie = TOMB) |
| **TOMB** | zimny atom w jądrze; **vacuum** = zanik |

---

## Co domknięte w tej linii sesji

| Obszar | Stan |
|--------|------|
| Tor B wzorzec | rustc + crate’y: `verify_rebuild` + G0/CI (slab→shell→kcc); plan `TOR_B_WDROZENIE.md` |
| kcc 0.6.2 + TB.4 P0–4 | minister K0; nie slot gcc |
| shell 0.3.2 + lifecycle T×reach | STAGE2 green |
| heat WRITE / strdup / dead code | fix |
| KANON król/minister/userspace | docs |
| SUBSTRATE_SEAL + STRICT | `KARMAZYN_SUBSTRATE_STRICT=1` |
| Karmin_DB | minister skarbu; `open_store` → native |

### Env uszczelnienia

```text
KARMAZYN_SUBSTRATE_STRICT=1
# golden only:
# KARMAZYN_ALLOW_PYTHON_SUBSTRATE=1
# KARMAZYN_SUBSTRATE=python
```

---

## Bramki

```powershell
cd C:\Users\drwis\KarmazynOs
.\native\stage1_verify.ps1
.\native\stage2_verify.ps1
.\toolchain\verify_kcc.ps1
```

---

## Next (gdy wrócisz)

1. **H0+H2a** start = native shell + mini-Lisp `(` ; klient Python = `native/ksub_client.py`
2. **Opc.** product: STRICT default gdy native; CI grep `import Store` bokiem  
2. **Opc.** View / export JSON (projekcja user zone)  
3. **Opc.** dopisać do KANON § sygnatura S + zamrożenie vs TOMB (ustalone słownie)  
4. **Nie** własny rustc / TB.5 z inercji — wzorzec jedzie na host `rustc`  
5. **Stop** — bramki zielone wystarczą  

---

## Untracked (nie commitować w torze A/B)

`out/`, `dist/`, bubble WIP, media w DBase  

---

*Sesja zamknięta w Holon (close + fact). Start: boot Karmazyn + KANON.md.*
