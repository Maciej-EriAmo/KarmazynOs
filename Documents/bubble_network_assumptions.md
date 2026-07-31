# Założenia sieci bąblowej KarmazynOS

**Bubble-borne network — bąbel jako powierzchnia nośna informacji**

Wersja: 0.4 (założenia + odniesienie implementacyjne)  
Status: dokument granicy / theory-of-ops  
Powiązania: HSS, HSL, substrat (atom, T, reach-GC), gość Lua; implementacja: DBase / KSH-1.2 / Cynober-Secure

---

## 1. Cel i zakres

### 1.1 Co ta sieć jest

Sieć, w której **nośnikiem informacji nie jest fala radiowa ani gniazdo IP**, lecz **bąbel** — stabilna, termiczna powierzchnia, na której informacja może się utrzymać, stygnąć i być widoczna tylko dla uprawnionych obserwatorów (geometria sesji + pryzmaty).

### 1.2 Co ta sieć nie jest

- Nie jest zamiennikiem **802.11 / Wi‑Fi** jako fizyki radia.
- Nie jest pełnym stackiem TCP/IP „od zera”.
- Nie obiecuje lepszych anten, roamingu ani odporności na jamming RF.

Opcjonalny spód (Ethernet, Wi‑Fi, loopback, plik, IPC) może **synchronizować lub transportować bąble między maszynami**. To hydraulika. Ontologia łącza pozostaje bąblowa.

### 1.3 Metafora naprawiona

| Potocznie mówimy | Znaczenie w tym dokumencie |
|------------------|----------------------------|
| „zamiast Wi‑Fi” | zamiast modelu **zaufanej sieci lokalnej opartej o adresy i broadcast** |
| „fale w bąblu” | **interferencja / rezonans śladów** w przestrzeni Φ, nie EM |
| „łącze wstało” | istnieje **żywa, współwidoczna powierzchnia bąbla** powyżej progów |

---

## 2. Aksjomaty

**A1 — Nośnik jest bąblem.**  
Informacja nie „leci do adresu”; **stabilizuje się na powierzchni**. Brak powierzchni = brak łącza w sensie modelu.

**A2 — Atom jest jednostką emisji i trwania.**  
Minimalny ładunek na nośniku to atom \(A = (S, E, T)\) (lub jego projekcja pryzmatyczna), nie ramka MAC.

**A3 — Widoczność ≠ dostarczenie.**  
Strona nie „dostaje pakietu”, tylko **może zarezonować** z tym, co leży na powierzchni (HSS: Trace, gate, sim). To, czego nie widać, w jej świecie **nie istnieje** (Warp Oblivion / pryzmat), a nie jest „forbidden”.

**A4 — Temperatura mówi KIEDY, osiągalność mówi CZY.**  
Prawo substratu obowiązuje na nośniku: zimny + nieosiągalny → znika; zimny + trzymany → retencja TOMB; brak ambient immortality w LAN.

**A5 — Brak ambient authority sieci.**  
Sam fakt „jestem podłączony do medium fizycznego” nie daje widoku powierzchni. Widok wynika z **sesji, Trace/Core, pryzmatu φ, polityki HSL**.

**A6 — Hydraulika pod spodem jest wymienna.**  
RF, kabel, pamięć współdzielona, replikacja dyskowa — to tylko sposoby uzgodnienia *tego samego* (lub zsynchronizowanego) bąbla. Nie dyktują semantyki.

**A7 — Bezpieczeństwo jest własnością powierzchni i sesji.**  
HSL chroni *interpretowalność* (pryzmaty, klucze sesji, oblivion). HSS steruje *kto w ogóle rezonuje*. To nie zastępuje fizycznej ochrony nośnika bitów.

---

## 3. Warstwy modelu

```
┌─────────────────────────────────────────────────────────────┐
│  L4  Aplikacja / gość (Lua, agenci, narzędzia)              │
├─────────────────────────────────────────────────────────────┤
│  L3  HSL — sesja, pryzmaty, crypto (np. Ring-LWE), oblivion │
├─────────────────────────────────────────────────────────────┤
│  L2  HSS — pole widoczności, Trace/Core, gate, emisja       │
├─────────────────────────────────────────────────────────────┤
│  L1  Nośnik bąblowy — powierzchnia, żywotność, T, reach     │
├─────────────────────────────────────────────────────────────┤
│  L0  Hydraulika (opcjonalna) — Wi-Fi, ETH, IPC, plik, mesh  │
└─────────────────────────────────────────────────────────────┘
         ↑ loader → jądro (substrat) → warstwa komunikacyjna
```

**Kanoniczna „sieć” w sensie KarmazynOS = L1–L3.**  
L0 istnieje tylko gdy trzeba przekroczyć jedną maszynę lub jeden proces.

---

## 4. Bąbel jako powierzchnia nośna

### 4.1 Definicja robocza

**Powierzchnia nośna** = bąbel \(B\) w substracie, który:

1. jest (lub bywa) **korzeniem / osiągalny** w sesjach uczestników,
2. trzyma wiązania atomów stanowiących **treść i ślady emisji**,
3. ma **politykę życia** (zanik T, max_age, reguły vacuum),
4. może być **unieważniony** (revoke → Warp Oblivion dla treści zależnej od klucza/pryzmatu).

### 4.2 Rodzaje powierzchni (założenie taksonomii)

| Rodzaj | Rola | Przykład użycia |
|--------|------|------------------|
| **Sesyjny** | krótkożyciowy nośnik rozmowy / zadania | dwa agenty, jedna sesja |
| **Domenowy** | dłuższy nośnik wspólnoty | „pokój”, zespół, device class |
| **Śladowy (H)** | anonimowe pole emisji bez nadawcy w semantyce | HSS pole H |
| **Prywatny** | powierzchnia jednego agenta; inni widzą tylko projekcje | notes / CORE |

Jeden agent może jednocześnie widzieć wiele powierzchni; **routing to wybór powierzchni + rezonans**, nie tablica IP.

### 4.3 Życie powierzchni

- **Utworzenie** — jawne (sesja HSL) lub emergentne (pierwsza emisja do uzgodnionego bąbla).
- **Utrzymanie** — heat przy rezonansie / zapisie; settle i vacuum w tle.
- **Rozpad** — brak reach + niska T; albo revoke.
- **Replikacja (L0)** — kopia / sync stanu bąbla między węzłami; konflikt = reguła termiczna + wersja sesji, nie „ostatni write wygrywa” bez polityki.

---

## 5. Organizacja „fal” w bąblu

Tu „fala” = **ślad w przestrzeni wektorowej / korelacyjnej**, nie EM.

### 5.1 Emisja

Agent emituje na powierzchnię atom (lub pakiet pryzmatyczny) taki, że:

\[
\mathrm{sim}(\mathrm{msg}, \mathrm{Trace}_{\mathrm{sender}}) \approx \mathrm{emission\_sim}
\]

- niskie `emission_sim` → szept (tylko bliscy Trace),
- wysokie → szeroka widoczność, większy koszt tożsamości / konwergencji (tradeoff HSS).

### 5.2 Interferencja

Wiele emisji **składa się** na stan powierzchni (bundle / hologram / suma śladów).  
Brak kolejki FIFO jako ontologii pierwotnej; kolejność może być wtórna (epoch, T, monotoniczny licznik sesji).

### 5.3 Selekcja (odbiór)

Odbiorca pobiera z powierzchni to, dla czego:

\[
\mathrm{sim}(\mathrm{atom}, \mathrm{Trace}_{\mathrm{recv}}) > \mathrm{gate}
\quad \wedge \quad
\text{polityka HSL (pryzmat, sesja) pozwala}
\]

Poniżej progu: **cisza ontologiczna**, nie ICMP unreachable.

Analityczny crossover (z HSS):

\[
\mathrm{core\_overlap}(A,B) > \frac{\mathrm{gate}}{\mathrm{emission\_sim}}
\]

### 5.4 Tłumienie

- **Termiczne** — zanik \(T\), vacuum decay.
- **Wiekowe** — `max_age` epok na polu H.
- **Sesyjne** — wygaśnięcie klucza / epoch.
- **Administracyjne** — revoke bąbla lub pryzmatu.

### 5.5 Multipleks „kanałów”

Nie pasma GHz, lecz:

- **pryzmaty** (CORE / IN / OUT / …),
- **podpowierzchnie** (sub-bąble lub etykiety w bąblu),
- **głośność emisji** (`emission_sim`),
- **budżet sesji** (limit ticków / atomów na powierzchnię).

### 5.6 Czego fale bąblowe nie robią

Nie zapewniają same z siebie: bitowego multipleksu RF, anti-jamming, garantowanego pasma fizycznego, geolokalizacji anteny.

---

## 6. HSS na powierzchni nośnej

### 6.1 Rola HSS

HSS odpowiada na pytanie: **kto w ogóle może zobaczyć ruch na bąblu jako sensowny sygnał?**

Komponenty (zgodnie z modelem HSS):

- **Core** — stały rdzeń tożsamości agenta,
- **Trace** — dynamiczny ślad (ewolucja przez interakcje),
- **pole / powierzchnia** — bąbel (lokalnie) lub H (anonimowe emisje),
- **gate** — próg przeżycia / widoczności.

### 6.2 Założenia routingu

1. Brak adresów IP/MAC jako pierwotnych.
2. Routing jest **binarny względem gate** (powyżej — widać, poniżej — zero w świecie odbiorcy).
3. Intensywność emisji steruje kompromisem **tożsamość ↔ zasięg**.
4. Agent nie odbiera własnych emisji jako obcych (niezmiennik HSS).

### 6.3 Threat model (HSS)

| Zagrożenie | Znaczenie |
|------------|-----------|
| Węzeł z bliskim Trace | może rezonować „za blisko” — to główny atak semantyczny |
| Flood powierzchni | DoS termiczny / budżetowy — wymaga limitów L1 |
| Podsłuch hydrauliki L0 | widzi szyfrogramy/bity, niekoniecznie sens (jeśli HSL trzyma) |
| Kradzież Core/kluczy | klasyczny compromise endpointu |

---

## 7. HSL na powierzchni nośnej

### 7.1 Rola HSL

HSL odpowiada na pytanie: **nawet gdy widać, że „coś jest”, czy wolno to zinterpretować jako treść?**

Założenia:

1. Treść na powierzchni może być **pryzmatycznie zaszyfrowana** (np. Ring-LWE / LPR w modelu Karmazyn).
2. Agent bez pryzmatu dostaje **szum lub nieistnienie**, nie plaintext + deny.
3. **No-plaintext-in-kernel** (gdy most do hosta/LSM): decyzja w daemonie sesji, egzekucja w granicy.
4. **KDF attenuation** — klucze agentów pochodne od sesji i zadania; mały blast radius.
5. **Revoke** powierzchni lub pryzmatu = kryptograficzne i ontologiczne zerwanie nośnika treści.

### 7.2 Intuicja „bezpieczniej niż Wi‑Fi”

Dotyczy **modelu zaufania do sieci lokalnej**, nie odporności radia:

- brak domyślnego broadcastu sensownego do wszystkich w SSID,
- widoczność geometryczna + sesyjna,
- oblivion zamiast samej ACL,
- (w modelu) post-kwant na sesji/pryzmacie.

Nadal trzeba chronić L0 (kanał bitów) i endpointy.

---

## 8. Jednostki protokołu (kontrakt logiczny)

Bez API kodu — kontrakt pojęciowy:

| Pojęcie | Znaczenie |
|---------|-----------|
| **Surface** | bąbel-nośnik z id sesji/domeny |
| **Emit** | połóż atom/ślad na Surface z danym `emission_sim` |
| **Sense** | odczytaj z Surface to, co > gate i dozwolone pryzmatem |
| **Heat** | interakcja podnosi T (utrzymanie) |
| **Settle** | epoka zaniku / vacuum na Surface |
| **OpenSession** | uzgodnij Surface + materiał HSL (klucze, epoch) |
| **Revoke** | unieważnij Surface lub pryzmat |
| **Budget** | limit atomów / emisji / ticków na Surface |

Opcjonalnie L0:

| Pojęcie | Znaczenie |
|---------|-----------|
| **SyncSurface** | przenieś/zmerguj stan bąbla między węzłami |
| **Carrier** | opis hydrauliki (local, eth, wifi, file…) — poza ontologią |

---

## 9. Mapowanie na start systemu

```
loader
  → jądro (substrat: atomy, bąble, reach-GC, tick)
  → warstwa komunikacyjna (shell + gość; surface API)
  → (opcjonalnie) HSS/HSL daemony sesji
  → (opcjonalnie) L0 sync
```

Sieć bąblowa **nie wymaga** osobnego „stacku Wi‑Fi w jądrze”.  
Wymaga: **bąbli jako nośników**, reguł T/reach, reguł widoczności (HSS), reguł interpretacji (HSL).

---

## 10. Założenia niefunkcjonalne

1. **Determinizm progów** — gate / emission parametry są częścią kontraktu sesji, nie magią.
2. **Budżety** — każda Surface ma limity; brak limitu = DoS na Φ.
3. **Obserwowalność operatorska** — meta OS (`:stats`, `:ls`, …) widzi nośniki; gość widzi tylko to, co pryzmat pozwala.
4. **Degradacja** — bez HRR/numpy: sieć może działać w trybie uproszczonym (np. etykiety + T bez pełnej geometrii); pełne HSS wymaga twarzy wektorowej.
5. **Przenośność nośnika** — ta sama ontologia na jednej maszynie (IPC bąbli) i na wielu (sync L0).
6. **Gość skryptowy** — Lua jest domyślnym językiem narzędzi operujących na Surface; nie jest częścią L0.

---

## 11. Świadomie poza zakresem (v0.1)

- Specyfikacja bitowa ramek L0  
- Konkretne algorytmy merge konfliktów multi-master  
- Implementacja Ring-LWE / wybór NIST PQC  
- Mapowanie na netdev / Android / radio SoC  
- Gwarancje czasu rzeczywistego  
- Ekonomika spektrum radiowego  

---

## 12. Kryteria sukcesu założeń (kiedy model „działa”)

Model uznajemy za spójny, gdy:

1. Dwa agenty **bez wspólnego adresu** mogą wymieniać sens przez wspólną Surface.  
2. Trzeci agent **bez Trace/pryzmatu** nie buduje z tego ontologii (cisza / szum).  
3. Stygniecie i revoke **usuwają łącze** w sensie modelu, nie tylko „zamykają socket”.  
4. Wymiana Carrier L0 (np. z loopback na plik sync) **nie zmienia** semantyki Emit/Sense.  
5. Bezpieczeństwo da się opisać bez odwołań do SSID — wyłącznie Surface + HSS + HSL.

---

## 13. Hipoteza szersza: wpływ na sieci bezprzewodowe

Ten rozdział jest **hipotezą strategiczną**, nie wymogiem implementacji KarmazynOS.
Służy do myślenia o skali pomysłu: bąbel-nośnik może zmienić nie tylko nasz runtime,
lecz **sposób działania sieci bezprzewodowych jako systemów zaufania i widoczności**.

### 13.1 Precyzja tezy

Model **może** zmienić organizację sieci bezprzewodowych w sensie:

> niekoniecznie „inne fale w powietrzu”, tylko inna organizacja tego, **co sieć bezprzewodowa w ogóle robi**.

Nie obiecuje nowej fizyki anten. Obiecuje (hipotetycznie) nową **hierarchię łącza**.

### 13.2 Odwrócenie hierarchii

**Dziś** (typowy Wi‑Fi / komórka):

```text
jestem w zasięgu radia → jestem w sieci → (prawie) wspólna ontologia bitów
```

**Po modelu powierzchni nośnej:**

```text
mam powierzchnię / sesję / rezonans → mam łącze znaczenia
radio jest tylko jednym z możliwych L0
```

To nie optymalizacja 802.11. To zmiana pytania z:

> „jak dowieźć pakiet?”

na:

> „jak długo i dla kogo informacja w ogóle istnieje we wspólnym polu?”

### 13.3 Co mogłoby się zmienić w praktyce sieci bezprzewodowych

| Dziś | Po „rewolucji powierzchni” |
|------|----------------------------|
| SSID + hasło = klub bitów | **bąbel / sesja** = klub widoczności |
| broadcast w komórce | **szept geometryczny** (gate / emission) |
| ACL i firewall nad IP | **pryzmat + oblivion** (nieistnienie w świecie agenta) |
| roaming = trzymanie IP / sesji L2–L4 | roaming = **utrzymanie powierzchni i Trace**, nie adresu |
| „bezpieczna sieć” = szyfrowany kanał | „bezpieczna sieć” = **kto w ogóle może złożyć sens** |
| urządzenie w LAN domyślnie głośne | urządzenie domyślnie **ciche ontologicznie** |

Gdyby bąbel-nośnik + HSS/HSL stały się warstwą *nad* (albo *zamiast* w ontologii)
klasycznego „LAN w eterze”, sieć bezprzewodowa przestałaby być przede wszystkim
**wspólną rurą bitów**, a stała się **zbiorem termicznych powierzchni widoczności**.

### 13.4 Czego sama w sobie hipoteza nie zmienia

- spektrum, interferencji EM, mocy nadawania, reguł regulatora,
- faktu, że sniffer i tak widzi energię w eterze,
- fizycznego jammingu i twardych limitów baterii / duty cycle,
- równań Maxwella i warstwy PHY jako inżynierii radia.

Czyli:

- **tak** — rewolucja modelu zaufania, adresacji i „bycia w sieci” w radiu;
- **nie** — automatyczna rewolucja fizyki bezprzewodowej.

### 13.5 Dwie skale myślenia (dyscyplina)

| Skala | Pytanie | Status w tym dokumencie |
|-------|---------|-------------------------|
| **KarmazynOS** | Czy bąbel-nośnik jest prawdą o *naszej* sieci? | założenia robocze (v0.x) |
| **Sieci bezprzewodowe w ogóle** | Czy to przepis na *wszystkie* sieci radiowe? | hipoteza — wymaga osobnego przemyślenia |

Zasada: **najpierw domknąć skalę KarmazynOS; dopiero potem rościć skalę branżową.**
Pośpiech w drugiej skali psuje pierwszą (łatwo zlać radio z ontologią).

### 13.6 Jednozdaniowa hipoteza branżowa

**Sieć bezprzewodowa mogłaby przestać być wspólną rurą bitów w zasięgu radia, a stać się zbiorem termicznych powierzchni widoczności — radio pozostałoby hydrauliką L0, a łącze znaczenia wynikałoby z bąbla, sesji i rezonansu, nie z samego faktu bycia w SSID.**

---

## 14. Zakłócenia informacji w modelu bąblowym

Ten rozdział rozdziela to, co w klasycznych sieciach (i w potocznym „jammingu”)
często leży w jednej kupie: **zakłócenie fizyczne** vs **zakłócenie informacyjne /
poznawcze**. Model powierzchni nośnej zmienia głównie drugie — kosztem nowych wektorów ataku.

### 14.1 Co dziś miesza się pod słowem „zakłócenie”

| Rodzaj | Przykład |
|--------|----------|
| fizyczne | jamming RF, szum EM, kolizja w kanale |
| transportowe | utrata ramek, retransmisje, congestion |
| informacyjne | fałszywy pakiet, spoof, flood sensem |
| poznawcze | „widzę śmieci, więc nie wiem, co jest prawdą” |

W sieci bąblowej te warstwy mapują się inaczej (patrz §14.5).

### 14.2 Zakłócenia fizyczne (L0) — prawie bez zmiany ontologii

Zagłuszenie radia, słaby SNR, interferencja w spektrum **dalej bolą hydraulikę** (Carrier / SyncSurface).

Różnica modelowa:

- to nie jest od razu „sieć padła w sensie znaczenia”;
- to: wolniejszy / urwany sync Surface, mniej heat, szybsze stygniecie, ewentualny rozpad repliki bąbla;
- **łącze znaczenia** może nadal istnieć lokalnie (jeden węzeł, lokalna Surface), nawet gdy radio milczy.

**Wniosek:** zakłócenie L0 psuje **uzgodnienie powierzchni między węzłami**, nie definicję tego, czym jest łącze.

### 14.3 Zakłócenia informacyjne — gdzie model realnie zmienia grę

#### A. Broadcast / szum sąsiedztwa (klasyczny LAN)

Dziś: głośny host zaśmieca wszystkich w SSID (skany, mDNS, ARP flood sensem).

Na Surface:

- emisja bez rezonansu z Trace **nie wchodzi do świata** odbiorcy (poniżej gate = cisza ontologiczna);
- „śmieć w eterze” ≠ „śmieć w mojej Φ”.

**Efekt:** duża klasa zakłóceń informacyjnych z sąsiedztwa radiowego **wypada z ontologii agenta**, o ile gate i Trace trzymają.  
Sniffer nadal może widzieć bity L0; agent **nie musi** budować z nich faktów.

#### B. Fałszywa treść / wstrzyknięcie

Dziś: spoof w LAN, zły host, podmieniony pakiet „w klubie SSID”.

Tu sensowny atak informacyjny wymaga raczej:

- emisji **bliskiej Trace** ofiary (wejście w geometrię HSS),
- albo kompromitacji pryzmatu / sesji (HSL),
- albo floodu **powyżej gate** na wspólnej Surface.

Sam fakt bycia w zasięgu radia / na tym samym Carrier **nie wystarcza**, by stać się faktem w Φ.

#### C. Oblivion zamiast „zepsutego kanału z resztkami”

Gdy Surface lub pryzmat pada (revoke, vacuum, wygaśnięcie sesji):

- klasycznie: half-open state, stale cache, zombie po łączu;
- tu: treść **przestaje istnieć w świecie agenta** (Warp Oblivion / brak pryzmatu).

**Efekt:** mniej residualnego szumu poznawczego po zerwanym łączu — model faworyzuje **zniknięcie** nad **gniciem**.

#### D. Termika jako filtr zakłóceń w czasie

Ślady nieogrzewane stygną i wypadają z powierzchni (T, max_age, vacuum).

- spam / jednorazowy szum → krótki half-life na Surface;
- prawdziwa interakcja → heat, dłuższe trwanie.

To **filtr czasowy zakłóceń informacji**, którego sam IP TTL nie realizuje (TTL ≠ rezonans + T).

### 14.4 Nowe rodzaje zakłóceń (cena modelu)

Model nie usuwa zakłóceń — **przesuwa je** na geometrię i powierzchnię:

| Nowe zakłócenie | Opis |
|-----------------|------|
| **Zanieczyszczenie Trace** | długotrwały kontakt z obcymi emisjami ciągnie Trace → łatwiej o fałszywy rezonans (tradeoff tożsamość ↔ komunikacja HSS) |
| **Flood powierzchni** | masa atomów na Surface → DoS budżetu / Φ, nawet bez sensownej treści |
| **Szept-kolizja** | wielu „bliskich” agentów przy zbyt niskim gate → wzajemne zalewanie szeptem |
| **Fałszywy bliźniak** | adversary celowo zbliża wektor / Trace do ofiary |
| **Desync Surface** | L0 gubi sync → rozjechane repliki bąbla (fork rzeczywistości między węzłami) |
| **Oblivion jako atak** | revoke lub kradzież klucza sesji = „zagłuszenie przez nieistnienie” całej domeny treści |

**Mniej:** szumu z obcego radia jako faktów w Φ.  
**Więcej:** wojny o geometrię, budżet powierzchni i spójność replik.

### 14.5 Warstwowy model zakłóceń

```text
zakłócenie_fizyczne      → psuje L0  (nośnik bitów / sync Carrier)
zakłócenie_powierzchni   → psuje L1  (budżet, T, vacuum, revoke Surface)
zakłócenie_widoczności   → psuje L2  HSS (gate, Trace, fałszywy rezonans)
zakłócenie_interpretacji → psuje L3  HSL (pryzmat, sesja, wyciek plaintextu)
```

Klasyczne Wi‑Fi często sprowadza odporność do wariantu L0 + „crypto na rurze”.  
Tu **odporność na zakłócenia informacji** rośnie głównie na L2–L3:  
śmieć bez rezonansu i bez pryzmatu nie staje się faktem.

### 14.6 Założenia projektowe wynikające z §14

1. **Budżet Surface jest częścią bezpieczeństwa** — nie tylko QoS (§10).  
2. **Gate / emission_sim** to dźwignie antyzakłóceniowe, nie tylko parametry wygody.  
3. **Heat tylko od uprawnionego rezonansu** — inaczej adversary grzeje śmieci i przedłuża spam.  
4. **Detekcja zbliżania Trace** (dryf tożsamości) jest elementem threat modelu HSS.  
5. **Polityka merge przy desync** replik Surface musi być jawna — milczący fork to zakłócenie rzeczywistości.  
6. **Revoke** chroni przed gnicie stanu, ale sam staje się wektorem DoS — wymaga kontroli HSL / quorum sesji.

### 14.7 Jednozdaniowe podsumowanie (zakłócenia)

**Model bąbla działa na zakłócenia informacji jak sito ontologiczne: obcy szum radiowy i broadcast rzadziej wchodzą do świata agenta, treść stygnie i znika zamiast gnić, lecz pojawiają się nowe zakłócenia — zanieczyszczenie Trace, flood powierzchni, fałszywy rezonans, desync bąbla oraz oblivion jako broń.**

---

## 15. Odniesienie implementacyjne: Karmazynowy uścisk (DBase)

Ten rozdział **nie zastępuje** kodu ani manuala Cynober. Mapuje pojęcia sieci bąblowej
(§1–§14) na **już istniejący** protokół w repozytorium DBase — żeby teoria nie wisiała
w próżni i żeby ewolucja (żywy klucz termiczny, Surface API) szła od realnego brzegu.

### 15.1 Gdzie leży implementacja

| Komponent | Ścieżka (kanonicznie: `C:\Users\drwis\DBase`) | Rola |
|-----------|-----------------------------------------------|------|
| **Karmazynowy uścisk KSH-1.2** | `karmazyn_handshake.py` | symetryczny A↔B: krypto + wymiana phi-space + merge |
| **Cynober-Secure-1.2** | `cynober_rpc.py` | wire: handshake → HSL → KarminQL RPC |
| **HSS (Ring-LWE KEM)** | `karmazyn_hss.py` (+ `karmazyn_hss_ntt.py`) | negocjacja klucza post-kwant (profile proto/standard/production) |
| **HSL** | `karmazyn_hsl.py` | sesja: Φ², epoka, PrismMask, AAD, opcjonalny QKD-seed |
| **Klient / serwer** | `cynober_client.py`, `cynober_server.py`, `Cynober_db.py` | punkty dostępowe do przestrzeni |
| **Manual / papiery** | `cynober_manual.md`, `HSS_Paper_v2.5.0_PL.md`, `HSL_Paper_v1_1_0_EN.md` | kontrakt i teoria kryptograficzna |
| **Testy** | `tests/test_hss_handshake.py`, `test_hsl_session.py`, `test_hss_profiles.py` | regresja uścisku i sesji |

Powitanie protokołu (KSH): wersja m.in. `KSH-1.2`.  
Wire bazodanowy: `Cynober-Secure-1.0` / `1.1` / `1.2` (negocjacja wersji + anty-replay).

### 15.2 Fazy uścisku KSH-1.2 ↔ pojęcia Surface

Z nagłówka `karmazyn_handshake.py` (protokół symetryczny: po uścisku oba węzły mają
wspólny / scalony phi-space):

| Faza KSH | Co robi | Pojęcie sieci bąblowej (§8) |
|----------|---------|------------------------------|
| **0 Powitanie** | wersja, `node_id`, capability flags | rozpoznanie punktów dostępowych; caps = oferta Carrier/sesji |
| **1 Kryptografia** | HSS → ECDH → PBKDF2 fallback | **OpenSession** na brzegu; materiał klucza sesji (dziś bez profilu cieplnego w KDF) |
| **2 Serializacja** | phi-space → JSON (atomy: id, T, S, E, state, age, T_max, …) | snapshot **Surface / Φ** do transferu |
| **3 Wymiana** | wzajemny transfer zaszyfrowanych blobów (+ zlib) | **SyncSurface** po L0 (TCP) |
| **4 Scalenie** | union atomów; konflikt → **wyższe T wygrywa** + MAC confirm | reguła termiczna merge; potwierdzenie spójności powierzchni |

Transport L0 w KSH/Cynober: **TCP**, framing `uint32 BE length` + payload JSON (po krypto: ciphertext).  
To jest **Carrier**, nie ontologia łącza (§1.2, §3 L0).

### 15.3 Mapowanie kontraktu logicznego (§8) → API / zachowanie DBase

| Pojęcie (§8) | Odpowiednik implementacyjny (przybliżony) |
|--------------|-------------------------------------------|
| **Surface** | lokalny phi-space / Store sesji; po uścisku — union atomów; w Cynober v7.1+ także **świat** (`WYBIERZ ŚWIAT`) jako dłuższa powierzchnia współdzielona |
| **OpenSession** | `perform_handshake` / fazy 0–1 KSH + ustanowienie linku HSL |
| **Emit** | zapis atomu do Store / UTRWAL (KarminQL) w kontekście sesji — treść ląduje na powierzchni widocznej dla uprawnionej sesji |
| **Sense** | odczyt / WYPISZ / rezonans w granicach pryzmatu i stanu HSL; zła sesja → błąd GCM / brak rezonansu (kolaps do szumu) |
| **Heat** | operacje na atomie podnoszące T (touch / aktywność); merge faworyzuje gorętszy |
| **Settle** | tick / vacuum substratu na lokalnym Store (nie jest ramką protokołu wire) |
| **Revoke** | koniec sesji HSL / utrata klucza / zamknięcie tunelu; pełne Warp Oblivion bąbla — osobne ścieżki (m.in. gossip SOUL / administracja świata) |
| **Budget** | rate limit połączeń i zapytań (firewall / `cynober_rate_limit`) — analog budżetu Surface na brzegu RPC |
| **SyncSurface** | faza 2–4 uścisku; oraz ścieżki replikacji / gossip (manifest-first, shardy) dla dłuższych powierzchni |
| **Carrier** | TCP (LAN / Termux); PSK opcjonalnie (`KARM_PSK`); QKD-seed slot (`KARM_QKD_SEED`) |

### 15.4 Warstwy L0–L4 na stacku Cynober

```text
L4  KarminQL / GameStore / narzędzia CLI     ← aplikacja
L3  HSL (Φ², epoch, PrismMask, AAD, QKD)   ← interpretacja sesji
L2  HSS KEM + reguły widoczności sesji       ← kto wchodzi w sens (brzeg)
L1  phi-space / Store / atomy+T / (bąble*)   ← powierzchnia nośna
L0  TCP + length-prefix                      ← hydraulika
```

\* Bąble + bindings w pełnym sensie SOUL: osobna ścieżka (m.in. gossip), nie całość fazy 2 KSH
(KSH synchronizuje przede wszystkim **atomy phi-space w RAM**).

### 15.5 Threat model: przestrzeń vs punkty dostępowe (stan kodu)

Zgodnie z ustaleniem roboczym (§ rozmowa + §14):

| Stwierdzenie | Realizacja w DBase |
|--------------|-------------------|
| **Przestrzeń jest bezpieczna** (brak ambient LAN) | payload po wire to szum bez stanu HSL; brak równoległego HTTP/REST jako drugiego klubu bitów |
| **Atakuje się punkty dostępowe** | serwer/klient TCP, pliki konfiguracji, PSK env, kompromis urządzenia, flood na port |
| **Klucze utrudniają** | HSS Ring-LWE (+ profile), AES-GCM, PrismMask, PSK, opcjonalnie QKD-seed w KDF |
| **Splot / wiązanie sesji** | HSL: commit Φ², `s_target`, rezonans `hsl_cap`; rozjazd → brak tunelu |
| **Termika w protokole** | **merge by T** (żywa reguła treści); T w serializacji atomów |
| **Żywy klucz termiczny w HRR/KDF** | **nie zaimplementowany** — kierunek ewolucji (§15.7), nie stan v0.4 dokumentu |

### 15.6 Łańcuch kluczy HSL (skrót z manuala) vs „żywy klucz”

Dziś (Cynober / HSL):

```text
Φ² (per węzeł)           → commit = SHA256(Φ² ‖ link_nonce)
handshake (+ PSK?)       → shared_key
KARM_QKD_SEED?           → link_seed = HKDF(k_QKD ‖ shared_key)
PrismMask                → s_target = HKDF(link_seed, commit_A, commit_B, epoch, task, prisms)
ramka RPC                → frame_key = HKDF(s_target, AAD)
```

To już jest **sesyjny, epokowy** materiał (nie wieczne hasło SSID) — ale kotwicą są
Φ² / KEM / PSK / QKD, **nie trajektoria cieplna substratu**.

**Żywy klucz termiczny** (hipoteza robocza, spójna z § jądra „T mówi KIEDY”):

```text
K(t) ≈ HRR/HKDF( sekret_węzła  ⊛  H_thermal_okna(t)  ⊛  shared_key_lub_epoch )
```

- nie klucz na zawsze — **współewolucja** z oknem cieplnym i sesją;
- dump z chwili \(t_0\) starzeje się wraz z polem;
- nie zastępuje HSS; **dokłada** wiązanie brzegu do żywego Store.

### 15.7 Luki mapowania (uczciwy rejestr)

| Luka | Znaczenie dla ewolucji |
|------|------------------------|
| KSH sync ≠ pełny bąbel-SOUL | Surface w sensie §4 (bąbel) wymaga spięcia z gossip/SOUL lub rozszerzenia fazy 2 |
| Brak `H_thermal` w KDF | żywy klucz cieplny = przyszły input do Fazy 1 / HSL, nie obecny wire |
| Gate / emission_sim HSS agentowego | model HSS v0 (pole H, Trace) ≠ ten sam kod co KEM w `karmazyn_hss.py` — dwa poziomy „HSS” (sesja kryptograficzna vs przestrzeń agentów) |
| Multi-hop / mesh Surface | uścisk jest A↔B; siatka powierzchni = warstwa nad wieloma uściskami / gossip |
| Lua gość w KarmazynOS boot | nie jest stroną wire Cynober; może stać się L4 nad tym samym kontraktem Surface |

### 15.8 Zasada spójności dokumentów

1. **Zmiana ontologii** (bąbel-nośnik, fale, zakłócenia) → ten plik (`bubble_network_assumptions.md`).  
2. **Zmiana wire / KEM / HSL** → DBase (`karmazyn_handshake.py`, `karmazyn_hsl.py`, `cynober_rpc.py`, manual, papiery).  
3. **Nowa cecha** (np. thermal-bound key) → najpierw założenie tutaj (§15.6–15.7), potem kontrakt w manualu, potem kod i test.

### 15.9 Jednozdaniowe spięcie

**Karmazynowy uścisk w DBase (KSH-1.2 + Cynober-Secure-1.2) jest działającym OpenSession/SyncSurface nad TCP: przestrzeń Φ scalana termicznie (merge by T), brzeg chroniony HSS+HSL; sieć bąblowa z tego dokumentu to ontologia i kierunek ewolucji (Surface, żywy klucz cieplny, sitko zakłóceń), nie drugi równoległy protokół od zera.**

---

## 16. Jednozdaniowe podsumowanie (rdzeń modelu)

**Sieć KarmazynOS opiera się na bąblu jako termicznej, sesyjnie i pryzmatycznie chronionej powierzchni nośnej informacji; „fale” to rezonans śladów (HSS) pod polityką interpretacji (HSL), a nie organizacja spektrum Wi‑Fi — hydraulika L0 jest wymienna i spoza ontologii łącza.**

---

## 17. Historia

| Wersja | Data | Uwagi |
|--------|------|--------|
| 0.1 | 2026-07-25 | Pierwsze założenia: bąbel = powierzchnia nośna; HSS/HSL; rozróżnienie od Wi‑Fi PHY |
| 0.2 | 2026-07-25 | §13 hipoteza szersza: wpływ na sieci bezprzewodowe |
| 0.3 | 2026-07-25 | §14 zakłócenia informacji |
| 0.4 | 2026-07-25 | §15 odniesienie implementacyjne: KSH-1.2 / DBase / Cynober-Secure; mapowanie faz i luk (żywy klucz termiczny) |
|
