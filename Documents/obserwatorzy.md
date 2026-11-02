# Obserwatorzy — użytkownik, obserwator, superobserwator

**Status:** plan (półka PLAN w [KANON.md](KANON.md)) · **Data:** 2026-11-02 · założenia przyjęte 2026-11-02 (§ 5)  
**Po co:** podział dostępu w KarmazynOs w pojęciach substratu — widok, zasięg, pryzmat, klucz — a nie konta i bity uprawnień z Linuksa.

Podstawa: [bubble_network_assumptions.md](bubble_network_assumptions.md) — bąbel jest „widoczny tylko dla uprawnionych obserwatorów (geometria sesji + pryzmaty)”, a to, czego nie widać, „w jej świecie nie istnieje, a nie jest forbidden”. W HSS klucz agenta to `s_A = KDF(s_sess, agent_id, P_task)` ([ARCHITECTURE.pl.md](ARCHITECTURE.pl.md), § 3).

---

## 1. Trzy poziomy obserwacji

| | **Użytkownik** | **Obserwator** (≈ superużytkownik) | **Superobserwator** (≈ root) |
|---|---|---|---|
| Czym jest | agent z sesją na jednym bąblu | operator świata: zarządza, ale nie czyta | strażnik prawa i kluczy węzła, tylko w sytuacjach nadzwyczajnych |
| Klucz | `s_A` swojego bąbla | pryzmat obserwacji (meta) | `s_sess` / Φ², `master.key` — wyprowadza każde `s_A` |
| Widzi | swój bąbel-korzeń `B_u` i jego potomków, z treścią | kształt wszystkich bąbli: istnienie, rozmiar, T, reach; dziennik, servitory; treść tylko przez pryzmat udostępniony przez użytkownika | wszystko, także treść bąbli użytkowników |
| Nie widzi | reszty systemu — ona w jego świecie **nie istnieje** (pusty widok albo szum), bez „permission denied” | kluczy węzła, sesji HSS, treści bąbli użytkowników bez ich pryzmatu | — |
| Może | atomy, bąble i kod w `B_u`; **instalacja oprogramowania jednostkowego** (bąble kodu w `B_u`); własne servitory pod `B_u`; kod ogólny tylko powiązany przez obserwatora (`code.link` = nadanie zdolności) | zakładać i odbierać bąble użytkowników (odebranie = Warp Oblivion), **instalacja oprogramowania ogólnego** i wiązanie go z użytkownikami, `servitor up/down`, `sync` | **instalacja systemu i konfiguracja wstępna**, **bezpieczeństwo na poziomie enterprise**: `disk format`, prawo Store (decay, thermal), klucze węzła, profil HSS i servitor `hss`, mianowanie obserwatorów, revoke całego świata |

## 2. Zasady

1. **Nie ma tabeli uid/gid ani bitów rwx.** Widok to zasięg od korzenia tożsamości. Użytkownik nie dostaje odmowy — poza `B_u` po prostu nic nie istnieje w jego świecie.
2. **Rola wynika z klucza, nie z wpisu.** Kto ma `s_sess`, wyprowadzi każde `s_A`: superobserwator czyta treść, bo tak działa matematyka HSS, a nie dlatego, że flaga mu pozwala. Odebranie klucza (revoke) to oblivion treści od niego zależnej.
3. **Obserwacja ma znaczenie termiczne.** Odczyt w substracie grzeje (`HEAT_READ`). Obserwator patrzy bez grzania — inaczej samo zaglądanie podtrzymywałoby życie cudzych atomów i zaburzało T×reach użytkownika. Grzeje dopiero działanie.
4. **Superobserwator nie pracuje ciągle.** Skoro widzi wszystko, działa tylko w sytuacjach nadzwyczajnych: instalacja systemu i konfiguracja wstępna, bezpieczeństwo na poziomie enterprise. Na co dzień świat prowadzi obserwator, który zarządza, ale nie czyta. Superobserwator wchodzi z konsoli fizycznej (tty1 / ttyS0 PID 1) albo z kluczem węzła, nigdy przez sieć. Obserwator może działać zdalnie przez tunel Cynober.
5. **Shell pozostaje ministrem spraw wewnętrznych** (KANON): obserwator i superobserwator to tryby operatora jądra. Użytkownik to klient — widzi swój bąbel przez widok, a nie model jądra.
6. **Oprogramowanie ma dwa poziomy.** Ogólne instaluje obserwator: bąble kodu w bibliotece świata (dziś ziarno `lua_bin` i narzędzia), a użytkownik dostaje je przez powiązanie (`code.link`) — widzi tylko to, co mu powiązano. Jednostkowe instaluje użytkownik we własnym `B_u`; dla innych nie istnieje, obserwator widzi tylko jego kształt.

### Tryb nadzwyczajny superobserwatora (propozycja do potwierdzenia)

Z zasady 4 wynikają trzy rzeczy, w prawie Store:

- **Otwierany jawnie.** Sesja superobserwatora to atom w bąblu `tożsamości`, zakładany z konsoli po podaniu klucza węzła. Bez niego shell pracuje jako obserwator.
- **Wygasa sam.** Atom sesji stygnie w epokach jak każdy inny; po zejściu do COLD tryb się zamyka. Praca go nie podgrzewa, więc nie da się go utrzymywać w nieskończoność — trzeba go otworzyć od nowa.
- **Zostawia ślad.** Każde działanie trafia do dziennika jako wpis widoczny dla obserwatora (kształt i opis działania, bez treści bąbli użytkowników).

## 3. Czego brakuje w kodzie (stan 2026-11-02)

1. **Reach i `lookup` idą w górę przez rodziców.** Bąbel użytkownika z rodzicem w drzewie systemu widziałby powiązania rodzica. `B_u` musi być korzeniem bez rodzica, a widok musi zatrzymywać się na jego granicy — potrzebny jest widok w dół, którego substrat dziś nie ma.
2. **Jeden gość Lua na cały shell.** Wspólne zmienne globalne zdradziłyby jednego użytkownika drugiemu. Potrzebny osobny stan Lua na tożsamość, z `caller = B_u` i API przefiltrowanym do widoku.
3. **Shell działa zawsze jako superobserwator** — dokładnie odwrotnie niż zasada 4. Nie ma logowania ani tożsamości. Docelowo shell po starcie jest obserwatorem, a tryb nadzwyczajny trzeba otworzyć.
4. **Szyfrowanie treści kluczem `s_A`** zależy od fazy 3 HSS ([linux_hss_roadmap.md](linux_hss_roadmap.md)). Bez niego granica użytkownika jest logiczna (widok), a nie kryptograficzna.

## 4. Kolejność

1. **Tożsamości jako atomy.** Bąbel `tożsamości`, widoczny tylko dla superobserwatora; atom tożsamości: rola, id `B_u`, weryfikator klucza (nie hasło).
2. **Widok w substracie.** Każda operacja shella i gościa przez widok z korzeniem: użytkownik — drzewo `B_u` z treścią; obserwator — kształt całości (istnienie, rozmiar, T, reach) bez treści bąbli użytkowników i bez kluczy, odczyt bez grzania; superobserwator — wszystko.
3. **Tryb nadzwyczajny** superobserwatora: atom sesji w `tożsamości`, wygasanie przez stygnięcie, wpisy w dzienniku.
4. **Logowanie na konsoli** i znak zachęty zależny od roli (np. `u$` / `o$` / `k$`).
5. **Osobny gość Lua na tożsamość**; biblioteka oprogramowania ogólnego i instalacja jednostkowa w `B_u`.
6. **Pryzmat i szyfrowanie treści `B_u` kluczem `s_A`** — razem z fazą 3 HSS; pryzmat udostępniony przez użytkownika daje obserwatorowi wgląd w treść.

## 5. Decyzje i pytania

**Przyjęte 2026-11-02:**

- Założenia § 1–2.
- Obserwator widzi tylko kształt (istnienie, rozmiar, T) — samą strukturę. Treść tylko przez pryzmat udostępniony przez użytkownika. Obserwator zarządza, ale nie czyta.
- Superobserwator widzi wszystko, dlatego nie pracuje ciągle — tylko w sytuacjach nadzwyczajnych: instalacja systemu i konfiguracja wstępna, bezpieczeństwo na poziomie enterprise.
- Oprogramowanie ogólne instaluje obserwator, jednostkowe — użytkownik.

**Otwarte:**

- **Tryb nadzwyczajny** (§ 2): otwieranie z konsoli kluczem węzła, wygasanie przez stygnięcie atomu sesji, ślad w dzienniku — propozycja do potwierdzenia.
- **Mapowanie na role Karmin_DB** (`reader` / `writer` / `admin` w `cynober_world_auth.py`): użytkownik jako `writer` swojego świata, obserwator jako `admin`?
