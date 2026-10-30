# SESSION_CONTINUE — KarmazynOs (kontynuacja)

**Data:** 2026-10-30 (koniec sesji)  
**Repo Os:** `main` @ **`673c082`** (sesja: `377263d`…`673c082`, nic nie wypchnięte)  
**DBase:** `main` @ **`39f696e`** (2 poprawki protokołu z tej sesji, nie wypchnięte)  
**Kanon:** [`KANON.md`](KANON.md) — KarmazynOs to **nie** dystrybucja Linuksa: jądro Linuksa tylko nośnik (proces, sterowniki); system plików = bąble/atomy w formacie KAFD, sieć = Cynober-Secure/HSL do Karmin_DB.

---

## Stan płyty `out/karmazyn-linux.iso` (`scripts/build_linux_shell.ps1`)

| Obszar | Stan |
|--------|------|
| Konsola | ekran VGA (tty1) + serial (ttyS0) naraz, `KARMAZYN_CONSOLE=auto\|vga\|serial\|none` |
| Trwałość | Store = świat DBase `karmazyn_store_v1.4_kafx`: KAFD w kopercie KAFX w `/data/cynober/worlds/karmazyn.kafd` na ext4 (`/dev/vda` → `/data`); pusty dysk dostaje ext2 sam, inny tylko `disk format`; świat nieczytelny = zapis wstrzymany; autosync po zmianie treści |
| KAFD natywnie | `native/karmazyn_kafd`: v2.0/v2.1/KTIX/v1-odczyt, KAFS, dziennik, compact, KAFX/KX1, świat DBase (`world`, cecha `substrate`) — bajt w bajt z Pythonem |
| Sieć | `KARMAZYN_IP` / `KARMAZYN_GW` (grub.cfg: QEMU, host = 10.0.2.2), virtio_net |
| Karmin_DB | `native/karmazyn_cynober` (ECDH, HSS standard/production, HSL-1.1, PSK, QKD); w shellu `db connect / db <KarminQL> / db info / db close` |
| Narzędzia | Lua w `karmazyn.fs`: `tool` z `bin`, `require` z `lib`, `nano bin/x`, `edit <dir>/<plik>` (kursor) — **do przeróbki, patrz niżej** |

## Bramki / testy

```powershell
cd C:\Users\drwis\KarmazynOs
.\scripts\build_linux_shell.ps1          # płyta (toolchain GNU wybiera sam)
.\boot\linux\qemu_serial.ps1             # shell, Lisp, Lua, limit instrukcji
.\boot\linux\qemu_disk.ps1               # ext4 + świat KAFX przez restart (14+ punktów)
.\boot\linux\qemu_vga.ps1                # ekran + serial, zrzut out\karmazyn-vga.png
.\boot\linux\qemu_net.ps1                # sieć + db do żywego cynober_server.py
.\native\stage2_verify.ps1               # bramka shella (bąble po @etykiecie)
python native\karmazyn_kafd\cross\cross_check.py      # KAFD/KAFX/świat vs DBase
python native\karmazyn_cynober\cross\live_check.py    # klient vs żywy serwer DBase
```

---

## Do zrobienia w następnej sesji

1. **Narzędzia na model Karmazyna (zastrzeżenie użytkownika).** `bin`/`lib` w `karmazyn.fs`, `nano`, `edit`, `tool`, `require` to konwencje Unixa przeniesione na bąble. Najpierw ustalić z użytkownikiem, jak kod i narzędzia mają żyć w substracie (KANON: ministrowie przez szwy), potem przerobić — nie zgadywać.
2. **Sekrety sieci poza grub.cfg.** `KARM_PSK` (i ewentualnie `KARM_HSS_PROFILE`) z pliku w `/data/cynober` na dysku zamiast jawnie w linii jądra; domyślnie płyta idzie ECDH (HSS `standard` zerwałby połączenie z serwerem `proto`).
3. **ext2 bez księgowania.** Po twardym wyłączeniu jądro ostrzega „mounting unchecked fs”; rozważyć ext4 z journalem (formater albo `mke2fs` na płycie) albo prosty fsck.
4. **Dziennik KAFS na płycie.** Dziś każdy zapis podmienia cały świat (jak `save_documents`); przy większych światach dopisywać przyrostowo do `.kafs` i robić compact.
5. **Sieć na prawdziwym sprzęcie.** Brak DHCP (adres statyczny w grub.cfg); klawiatura USB może wymagać modułów, których `virt` nie ma — niesprawdzone.
6. **Polskie znaki na VGA.** Wbudowana czcionka konsoli nie ma ąęłó… (serial OK); np. font Lat2 przy starcie.
7. **Klient Cynober — braki.** Profil HSS `proto` (macierz z PCG64 NumPy) i media KAFS (put/get) nieobsługiwane.
8. **DBase.** Czerwony test `tests.test_kernel TestStore.test_nested_tick_is_noop` (był przed tą sesją). Wzmianka o natywnym KAFD i teście zgodności w `DBase/docs/KAFD.md` — czeka na zgodę (inne repo). Push obu repozytoriów — tylko na prośbę.
9. **Odłożone świadomie:** `rustc` na płycie / samobudowa ISO.

---

# Poprzednia sesja (2026-08-07) — archiwum

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
