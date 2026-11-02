# Mapa drogowa — Linux, moduł HSL, shell Karmazyna

**Status:** living · **Data:** 2026-10-19  
**Cel:** Karmazyn stoi na jądrze Linuksa jako niezależny system. HSL jest modułem nośnika, HSS jest servitorem w gościu, protokół sesji Φ nie jest drugim jądrem.

Ten plik jest planem realizacji. Zamknięta bramka fazy nie jest twierdzeniem, że działa cały system.

## Układ

```
GRUB
  → jądro Linuksa (konsola ttyS0, dysk, sterowniki)
       → moduł HSL  holo/holo_hsl.ko     (bramka fazy 2, GPL-2.0)
       → karmazyn_shell                 (Store + mini-Lisp, MIT, PID 1)
            → servitor hss              (bąbel kodu w gościu: sesja Φ, HMAC)
```

- Linux daje proces, pamięć, konsolę, dysk i sterowniki.
- HSL na płycie fazy 2 jest jednym modułem GPL. Jądro przenosi pytanie o uprawnienie i nie liczy HMAC. `holoPhiHss.c` zostaje źródłem na jądro złożone z łatą LSM.
- HSS jest servitorem: bąblem kodu w gościu Lua w PID 1, nie osobnym programem ani procesem nośnika. Protokół: klucz agenta, epoka, identyfikator inode, `capability_hint`.
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

Bez sesji Φ moduł odmawia `MAY_READ` i `MAY_WRITE` na inode z xattr `security.hss.lock`. Sesję w fazie 3 ustawi servitor HSS. Zapis `S` do `/dev/hss` jest tylko haczykiem tej bramki, nie HMAC.

**Bramka:** moduł się ładuje. Brak sesji daje odmowę. Shell z fazy 1 wstaje także bez modułu.

**2026-10-19:** bramka zamknięta. Osobna płyta `out/karmazyn-linux-hsl.iso`. Linux 6.18.57-0-virt. Serial: `HSL_LOADED`, `HSL_DENY`, `k$`, `(+ 1 2)` → `3`, `quit` → `pid 1 stays`. Skrypt `boot/linux/qemu_hsl.ps1` zakończył się kodem 0. Moduł nie ma podpisu Alpine i oznacza jądro jako tainted. To nie jest jeszcze upcall do servitora HSS. Płyta fazy 1 `out/karmazyn-linux.iso` zostaje bez tego modułu.

## Faza 3 — servitor HSS

**2026-11-02, decyzja:** HSS jest servitorem w gościu, nie demonem. Wcześniejszy plan (osobny program w przestrzeni użytkownika) jest nieaktualny.

Servitor `hss` to bąbel kodu z etykietą `hss`, powiązany z korzeniem `servitory` (jak każdy servitor: reach mówi czy, T mówi kiedy). Realizuje kontrakt upcall z `holoPhiHss.c`: sprawdza `HMAC(s_A, prism_id)` przeciw `capability_hint`.

Droga pytania: moduł HSL (nośnik) → `/dev/hss` → PID 1 → atom pytania w bąblu `hss` → krok servitora → odpowiedź przez PID 1 z powrotem do modułu. Proces nośnika jest tu tylko przewodem; decyzja zapada w gościu.

Klucz sesji nie jest atomem i nie trafia do gościa. Shell wkłada go przy starcie do keyringu PID, a gość dostaje od hosta samą operację HMAC (bez bajtów klucza). Zegar epoki jest wejściem decyzji: stempel z bąbla `czas`; cofnięty zegar nie otwiera sesji z innej epoki.

`extras/hss_demo.py` nie jest tym servitorem. To symulacja (wymiar 15, moduł 256).

**Otwarte przed bramką:**

1. Zegar epok PID 1. Dziś epoki płyną tylko przez `tick`/`settle`. Moduł czeka na decyzję, więc PID 1 musi odmierzać epoki sam albo dawać servitorowi krok, gdy przychodzi pytanie.
2. Czas odpowiedzi. Moduł potrzebuje limitu oczekiwania; brak odpowiedzi w limicie = odmowa.
3. API hosta dla gościa: HMAC na kluczu z keyringu, odczyt pytania i zapis odpowiedzi. Bez dostępu do samego klucza.

**Bramka:** zgodny hint przechodzi. Zły hint i brak sesji nie przechodzą. Decyzję widać jako krok servitora `hss` (`servitor`, `dziennik`).

## Faza 4 — złożenie płyty

Skrypt w `scripts/` składa jądro, initramfs, moduł i shell. Servitor HSS nie jest osobnym plikiem wykonywalnym: wchodzi jako bąbel kodu z ziarna. Wpis GRUB jest osobny od `boot/grub/grub.cfg` kentry. Test QEMU jest osobny od `boot/kentry/qemu_iso.ps1`: szuka `k$` i odmowy HSL, nie `KARMAZYN_KENTRY_OK`.

## Poza mapą

Własne jądro Karmazyna. System plików, w którym bąbel jest katalogiem. Flaga `immortal` jako format dysku. Python, Lua, Studio, `rustc` na płycie, `kcc`.

## Kolejność

Faza 1, potem 2, potem 3, potem 4. Moduł bez wstającego shella nie zamyka mapy.
