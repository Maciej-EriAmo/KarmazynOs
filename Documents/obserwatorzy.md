# Obserwatorzy — użytkownik, obserwator, superobserwator

**Status:** plan (półka PLAN w [KANON.md](KANON.md)) · **Data:** 2026-11-02  
**Po co:** podział dostępu w KarmazynOs w pojęciach substratu — widok, zasięg, pryzmat, klucz — a nie konta i bity uprawnień z Linuksa.

Podstawa: [bubble_network_assumptions.md](bubble_network_assumptions.md) — bąbel jest „widoczny tylko dla uprawnionych obserwatorów (geometria sesji + pryzmaty)”, a to, czego nie widać, „w jej świecie nie istnieje, a nie jest forbidden”. W HSS klucz agenta to `s_A = KDF(s_sess, agent_id, P_task)` ([ARCHITECTURE.pl.md](ARCHITECTURE.pl.md), § 3).

---

## 1. Trzy poziomy obserwacji

| | **Użytkownik** | **Obserwator** (≈ superużytkownik) | **Superobserwator** (≈ root) |
|---|---|---|---|
| Czym jest | agent z sesją na jednym bąblu | operator świata (dzisiejszy `k$`) | strażnik prawa i kluczy węzła |
| Klucz | `s_A` swojego bąbla | pryzmat obserwacji (meta) | `s_sess` / Φ², `master.key` — wyprowadza każde `s_A` |
| Widzi | swój bąbel-korzeń `B_u` i jego potomków | wszystkie bąble, T, reach, dziennik, servitory | wszystko, także treść bąbli użytkowników |
| Nie widzi | reszty systemu — ona w jego świecie **nie istnieje** (pusty widok albo szum), bez „permission denied” | kluczy węzła, sesji HSS, treści cudzych bąbli bez pryzmatu użytkownika (do rozstrzygnięcia, § 5) | — |
| Może | atomy, bąble i kod w `B_u`; własne servitory pod `B_u`; kod spoza `B_u` tylko powiązany przez obserwatora (`code.link` = nadanie zdolności) | zakładać i odbierać bąble użytkowników (odebranie = Warp Oblivion), wiązać kod, `servitor up/down`, `sync` | `disk format`, compact, prawo Store (decay, thermal), profil HSS i servitor `hss`, mianowanie obserwatorów, revoke całego świata |

## 2. Zasady

1. **Nie ma tabeli uid/gid ani bitów rwx.** Widok to zasięg od korzenia tożsamości. Użytkownik nie dostaje odmowy — poza `B_u` po prostu nic nie istnieje w jego świecie.
2. **Rola wynika z klucza, nie z wpisu.** Kto ma `s_sess`, wyprowadzi każde `s_A`: superobserwator czyta treść, bo tak działa matematyka HSS, a nie dlatego, że flaga mu pozwala. Odebranie klucza (revoke) to oblivion treści od niego zależnej.
3. **Obserwacja ma znaczenie termiczne.** Odczyt w substracie grzeje (`HEAT_READ`). Obserwator patrzy bez grzania — inaczej samo zaglądanie podtrzymywałoby życie cudzych atomów i zaburzało T×reach użytkownika. Grzeje dopiero działanie.
4. **Superobserwator tylko z konsoli fizycznej** (tty1 / ttyS0 PID 1) albo z kluczem węzła, nigdy przez sieć. Obserwator może działać zdalnie przez tunel Cynober.
5. **Shell pozostaje ministrem spraw wewnętrznych** (KANON): obserwator i superobserwator to tryby operatora jądra. Użytkownik to klient — widzi swój bąbel przez widok, a nie model jądra.

## 3. Czego brakuje w kodzie (stan 2026-11-02)

1. **Reach i `lookup` idą w górę przez rodziców.** Bąbel użytkownika z rodzicem w drzewie systemu widziałby powiązania rodzica. `B_u` musi być korzeniem bez rodzica, a widok musi zatrzymywać się na jego granicy — potrzebny jest widok w dół, którego substrat dziś nie ma.
2. **Jeden gość Lua na cały shell.** Wspólne zmienne globalne zdradziłyby jednego użytkownika drugiemu. Potrzebny osobny stan Lua na tożsamość, z `caller = B_u` i API przefiltrowanym do widoku.
3. **Shell działa zawsze jako superobserwator.** Nie ma logowania ani tożsamości.
4. **Szyfrowanie treści kluczem `s_A`** zależy od fazy 3 HSS ([linux_hss_roadmap.md](linux_hss_roadmap.md)). Bez niego granica użytkownika jest logiczna (widok), a nie kryptograficzna.

## 4. Kolejność

1. **Tożsamości jako atomy.** Bąbel `tożsamości`, widoczny tylko dla superobserwatora; atom tożsamości: rola, id `B_u`, weryfikator klucza (nie hasło).
2. **Widok w substracie.** Każda operacja shella i gościa przez widok z korzeniem: użytkownik — drzewo `B_u`; obserwator — całość bez kluczy, odczyt bez grzania; superobserwator — wszystko.
3. **Logowanie na konsoli** i znak zachęty zależny od roli (np. `u$` / `o$` / `k$`).
4. **Osobny gość Lua na tożsamość.**
5. **Pryzmat i szyfrowanie treści `B_u` kluczem `s_A`** — razem z fazą 3 HSS.

## 5. Do rozstrzygnięcia

- **Czy obserwator widzi treść bąbli użytkowników**, czy tylko ich kształt (istnienie, rozmiar, T)? Propozycja: samą strukturę; treść tylko przez pryzmat, który udostępni użytkownik — obserwator zarządza, ale nie czyta.
- **Czy superobserwator działa wyłącznie z konsoli fizycznej?**
- **Mapowanie na role Karmin_DB** (`reader` / `writer` / `admin` w `cynober_world_auth.py`): użytkownik jako `writer` swojego świata, obserwator jako `admin`?
