# SESSION_CONTINUE — KarmazynOs (kontynuacja)

**Data:** 2026-10-30  
**Repo Os:** `main`, kontynuacja od `4b0f9ec` (opis jedzie w commicie tej sesji)  
**DBase:** `master` @ **`39f696e`** (2 commity przed originem: `4eca597`, `39f696e`; push DBase czeka na prośbę)  
**Kanon:** [`KANON.md`](KANON.md) — jądro Linuksa jest nośnikiem (proces, sterowniki). System plików to bąble i atomy w KAFD. Sieć to Cynober-Secure/HSL do Karmin_DB.

---

## Stan płyty `out/karmazyn-linux.iso` (`scripts/build_linux_shell.ps1`)

| Obszar | Stan |
|--------|------|
| Konsola | ekran VGA (tty1) + serial (ttyS0) naraz, `KARMAZYN_CONSOLE=auto\|vga\|serial\|none` |
| Trwałość | Store = świat DBase `karmazyn_store_v1.4_kafx`: KAFD w kopercie KAFX w `/data/cynober/worlds/karmazyn.kafd` na ext4 (`/dev/vda` → `/data`); pusty dysk dostaje ext2 sam, inny tylko `disk format`; świat nieczytelny = zapis wstrzymany; autosync po zmianie treści |
| KAFD natywnie | `native/karmazyn_kafd`: v2.0/v2.1/KTIX/v1-odczyt, KAFS, dziennik, compact, KAFX/KX1, świat DBase (`world`, cecha `substrate`) — bajt w bajt z Pythonem |
| Sieć | `KARMAZYN_IP` / `KARMAZYN_GW` (grub.cfg: QEMU, host = 10.0.2.2), virtio_net; `KARM_PSK` i `KARM_HSS_PROFILE` z aktywnego profilu w `/data/cynober/client.json` (obok `master.key`); brak pliku = ECDH |
| Karmin_DB | `native/karmazyn_cynober` (ECDH, HSS standard/production, HSL-1.1, PSK, QKD); w shellu `db connect / db <KarminQL> / db info / db close` |
| Narzędzia | bąbel kodu: etykieta = nazwa, źródło w atomie `src` (E=`lua`, payload = bajty), bąbel jest korzeniem. `tool <etykieta>` woła najnowszy taki bąbel. `require` widzi bibliotekę z wołającego: powiązanie `code.link` albo etykieta na drodze rodzica. `nano <etykieta>` i `edit <etykieta>` edytują to źródło. `lua_bin/` jest ziarnem: PID 1 wchłania brakujące etykiety po wczytaniu świata (`narzędzia — N bąbli`). Skórka `karmazyn>` nadal odpala pliki z `lua_bin/`. `karmazyn.fs` zostaje na dokumenty |

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

## Domknięte w tej sesji

1. **Narzędzia są bąblami substratu.** Kod = bąbel-korzeń o etykiecie plus atom `src`. `tool` woła bąbel, `require` idzie po powiązaniu albo w górę rodziców. Ziarno `lua_bin` wchodzi do świata tylko jako PID 1, po wczytaniu świata, i tylko dla etykiet bez `src`. Stare pliki `bin/` i `lib/` w `karmazyn.fs` zostają dokumentami. Bramki: `stage2_verify.ps1`, `qemu_serial.ps1`, `qemu_disk.ps1`.
2. **Sekrety sieci są w pliku.** `KARM_PSK` i `KARM_HSS_PROFILE` z aktywnego profilu w `/data/cynober/client.json` (obok `master.key`). Brak pliku zostawia ECDH. Profil `proto` i pusty profil też zostawiają ECDH; `standard` przy serwerze na `proto` zrywa tunel. Środowisko ma pierwszeństwo przed plikiem. `KARMAZYN_IP` / `KARMAZYN_GW` zostają w `grub.cfg`. Bramki: `qemu_net.ps1` (ECDH, linii jądra bez tych sekretów) i `live_check.py`.

Szczegół narzędzi: [tools_lua.md](tools_lua.md).

## Do zrobienia w następnej sesji

1. **Dziennik na dysku.** Formater w `native/karmazyn_shell/src/ext2.rs` robi ext2 rev 1. Jądro montuje to jako ext4 i po twardym wyłączeniu pisze `mounting unchecked fs`. Dodać mały journal ext4 w tym samym formaterze (`disk format` i pierwszy pusty dysk). Istniejący świat ext2 zostaje czytelny. Bramka: `qemu_disk.ps1` plus twardy reset bez ostrzeżenia o niesprawdzonym systemie plików.
2. **Przyrostowy zapis KAFS.** `append_atom` i `compact_journal` już są w `native/karmazyn_kafd`. Autosync płyty nadal podmienia cały świat. Dopisywać zmiany do dziennika `.kafs` i robić compact po progu. Po compact treść świata ma być bajt w bajt z Pythonem. Bramka: `cross_check.py`, `qemu_disk.ps1`, test że zmiana jednego atomu nie przepisuje całej koperty.
3. **Polskie znaki na VGA.** Czcionka konsoli nie ma ąęćłńóśźż. Wczytać font Lat2 do VGA przy starcie. Serial zostaje. Bramka: `qemu_vga.ps1` i odczyt `out/karmazyn-vga.png`.
4. **Dwa braki klienta Cynober** (po dysku, bo zmieniają kontrakt na drucie). W `native/karmazyn_cynober`: profil HSS `proto` (macierz z PCG64, jak NumPy w DBase) i ramki KAFS (media put/get). Dziś `proto` spada do ECDH, a ramka KAFS jest odrzucana. Bramka: `python native/karmazyn_cynober/cross/live_check.py` przeciw żywemu `cynober_server.py`, w tym `proto` i jeden media put/get.

## Na prośbę, poza tą kolejką

- DBase: czerwony test `tests.test_kernel TestStore.test_nested_tick_is_noop` (był wcześniej). Wzmianka o natywnym KAFD w `DBase/docs/KAFD.md`. Dwa lokalne commity czekają. Push DBase osobno.
- DHCP i klawiatura USB na prawdziwym sprzęcie. Moduły `virt` pod to nie były sprawdzane.
- `rustc` na płycie, samobudowa ISO, własne jądro, faza G Store bez nośnika.
- Demon upcall HSL z mapy 19 października.
- Dopieszczanie gościa Lua 1.1.3 (`puc_subset`) — to host, nie ta płyta.
- `generate_from_idea` zostaje `nil`. `ThermalSurface.write(..., visible=True)` nie grzeje macierzy.

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
