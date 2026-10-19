# Mapa drogowa — Linux, moduł HSL, shell Karmazyna

**Status:** living · **Data:** 2026-10-19  
**Cel:** Karmazyn stoi na jądrze Linuksa jako niezależny system. HSS, HSL i protokół sesji Φ są modułem i procesem, nie drugim jądrem.

Ten plik jest planem realizacji. Nie jest twierdzeniem, że obraz już wstaje.

## Układ

```
GRUB
  → jądro Linuksa (konsola ttyS0, dysk, sterowniki)
       → moduł HSL  holo/holoPhiHss.c   (transport, GPL-2.0)
       → demon HSS                      (decyzja: sesja Φ, HMAC)
       → karmazyn_shell                 (Store + mini-Lisp, MIT, PID 1)
```

- Linux daje proces, pamięć, konsolę, dysk i sterowniki.
- HSL jest jednym modułem LSM. Jądro przenosi pytanie i nie interpretuje algebry HSS.
- HSS jest protokołem demona: klucz agenta, epoka, identyfikator inode, `capability_hint`.
- Silnik zostaje w przestrzeni użytkownika: `native/karmazyn_shell` linkuje `karmazyn_substrate` i `karmazyn_lisp`.
- Pliki leżą na systemie plików jądra (tmpfs albo ext4). Store nie jest formatem dysku.

Prompt tego obrazu to `k$`. Prompt `karmazyn>` zostaje przy skórze Pythona i nie jest bramką tej mapy.

## Bramka całości

QEMU bootuje płytę z `out/` (katalog jest w `.gitignore`). Serial COM1 pokazuje:

1. start jądra Linuksa,
2. załadowany jeden moduł HSL,
3. prompt `k$`,
4. wynik linii mini-Lispa,
5. odmowę dostępu do pliku, gdy nie ma sesji Φ.

Płyta kentry (`out/karmazyn-kentry.iso`, marker Multiboot2) zostaje osobno. Ten obraz jej nie zastępuje.

## Faza 1 — shell jako proces Linuksa

Z `native/karmazyn_shell` powstaje statyczny ELF `x86_64-unknown-linux-musl`. Initramfs niesie jądro virt i ten ELF jako `/init`. GRUB ładuje `linux` i `initrd`.

`quit` oraz koniec stdin na PID 1 zostawiają proces w pętli. Śmierć PID 1 zatrzymuje jądro.

**Bramka:** serial ma `k$`, a linia mini-Lispa wraca wynikiem. Moduł HSL jeszcze nie jest wymagany.

## Faza 2 — jeden moduł HSL

W `holo/` są dwa źródła: `holo_lsm.c` i `holoPhiHss.c`. Do obrazu wchodzi tylko `holoPhiHss.c`.

Moduł czyta z keyringu PID sesję Φ i `capability_hint`, potem pyta demona. Buduje się przy nagłówkach tego samego jądra, które jest na płycie. Plik jest na GPL-2.0 i nie jest linkowany do shella.

**Bramka:** moduł się ładuje. Brak sesji daje odmowę. Shell z fazy 1 wstaje także bez modułu.

## Faza 3 — demon HSS

Demon jest osobnym programem w przestrzeni użytkownika i realizuje kontrakt upcall z `holoPhiHss.c`. Sprawdza `HMAC(s_A, prism_id)` przeciw `capability_hint`.

`extras/hss_demo.py` nie jest tym demonem. To symulacja (wymiar 15, moduł 256). Klucz sesji wkłada shell przy starcie, przez keyring PID. Zegar epoki jest wejściem decyzji: cofnięty zegar nie otwiera sesji z innej epoki.

**Bramka:** zgodny hint przechodzi. Zły hint i brak sesji nie przechodzą.

## Faza 4 — złożenie płyty

Skrypt w `scripts/` składa jądro, initramfs, moduł, demona i shell. Wpis GRUB jest osobny od `boot/grub/grub.cfg` kentry. Test QEMU jest osobny od `boot/kentry/qemu_iso.ps1`: szuka `k$` i odmowy HSL, nie `KARMAZYN_KENTRY_OK`.

## Poza mapą

Własne jądro Karmazyna. System plików, w którym bąbel jest katalogiem. Flaga `immortal` jako format dysku. Python, Lua, Studio, `rustc` na płycie, `kcc`.

## Kolejność

Faza 1, potem 2, potem 3, potem 4. Moduł bez wstającego shella nie zamyka mapy.
