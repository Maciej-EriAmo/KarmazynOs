# Mapa drogowa — Linux, moduł HSL, shell Karmazyna

**Status:** living · **Data:** 2026-10-19  
**Cel:** Karmazyn stoi na jądrze Linuksa jako niezależny system. HSS, HSL i protokół sesji Φ są modułem i procesem, nie drugim jądrem.

Ten plik jest planem realizacji. Zamknięta bramka fazy nie jest twierdzeniem, że działa cały system.

## Układ

```
GRUB
  → jądro Linuksa (konsola ttyS0, dysk, sterowniki)
       → moduł HSL  holo/holo_hsl.ko     (bramka fazy 2, GPL-2.0)
       → demon HSS                      (decyzja: sesja Φ, HMAC)
       → karmazyn_shell                 (Store + mini-Lisp, MIT, PID 1)
```

- Linux daje proces, pamięć, konsolę, dysk i sterowniki.
- HSL na płycie fazy 2 jest jednym modułem GPL. Jądro przenosi pytanie o uprawnienie i nie liczy HMAC. `holoPhiHss.c` zostaje źródłem na jądro złożone z łatą LSM.
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

**2026-10-19:** bramka zamknięta. `out/karmazyn-linux.iso`, Linux 6.18.52-virt, `/init` = statyczny `karmazyn_shell`. Serial: `k$`, `(+ 1 2)` → `3`, `quit` → `pid 1 stays`. Skrypt `boot/linux/qemu_serial.ps1` zakończył się kodem 0.

## Faza 2 — jeden moduł HSL

`holo/holo_lsm.c` nie wchodzi na płytę. `holo/holoPhiHss.c` zostaje źródłem na jądro z łatą: `security_add_hooks()` w 6.18 jest `__init`, więc moduł po starcie nie rejestruje LSM.

Na jądro virt z płyty wchodzi `holo/holo_hsl.c`. To osobny plik GPL-2.0, nieslinkowany z shellem. Buduje się nagłówkami `linux-virt-dev` tego samego wydania co `vmlinuz`. Vermagic: `6.18.57-0-virt`.

Bez sesji Φ moduł odmawia `MAY_READ` i `MAY_WRITE` na inode z xattr `security.hss.lock`. Sesję w fazie 3 ustawi demon. Zapis `S` do `/dev/hss` jest tylko haczykiem tej bramki, nie HMAC.

**Bramka:** moduł się ładuje. Brak sesji daje odmowę. Shell z fazy 1 wstaje także bez modułu.

**2026-10-19:** bramka zamknięta. Osobna płyta `out/karmazyn-linux-hsl.iso`. Linux 6.18.57-0-virt. Serial: `HSL_LOADED`, `HSL_DENY`, `k$`, `(+ 1 2)` → `3`, `quit` → `pid 1 stays`. Skrypt `boot/linux/qemu_hsl.ps1` zakończył się kodem 0. Moduł nie ma podpisu Alpine i oznacza jądro jako tainted. To nie jest jeszcze upcall do demona. Płyta fazy 1 `out/karmazyn-linux.iso` zostaje bez tego modułu.

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
