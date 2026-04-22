# Genesis 5: Minimalna Pętla Generatywna

## Reprezentacja Zależna od Obserwatora poprzez Bramkowanie Strumienia Wejściowego w KarmazynMatrix

**Maciej Mazur (EriAmo)** · Niezależne Badania · Warszawa, Polska  
Kwiecień 2026 · Towarzysz KarmazynMatrix v3.4 · Kod: `genesis5.py`

---

## Abstrakt

Rozszerzamy KarmazynMatrix o minimalną pętlę generatywną: zewnętrzny strumień wejściowy, którego atomy są dopuszczane lub odrzucane przez geometryczną bramę, po czym stosowane są normalne dynamiki temperatury, zaniku i rezonansu. Próg bramy jest identyczny z warunkiem przeżycia ustalonym w v3.4 (`k·⟨S, Trace⟩ > λτ + f`), więc jedna nierówność rządzi zarówno wejściem jak i wyjściem. Atomy mają skończony czas życia (`max_age` epok), tworząc ciągłą rotację i pozwalając atraktorowi ewoluować.

Trzy eksperymenty charakteryzują powstały system. **(E1)** Populacja osiąga stabilną równowagę 27,5 ± 3,66 atomów, z integralnością śladu utrzymaną na poziomie core_sim = 0,9586 ± 0,0003 i quasi-statycznym dryftem śladu 0,000184/epokę. **(E2)** Nagły wrogi strumień — sygnał ortogonalny do aktualnego atraktora — jest całkowicie blokowany (0 atomów wpuszczonych); gdy przyjazne atomy wygasają, system oczyszcza się do stałego rdzenia, a core_sim poprawia się. **(E3)** Stopniowo obracający się strumień — przechodzący od wyrównania z rdzeniem do prostopadłości przez 100 epok — jest śledzony przez ślad z korelacją 0,9457, prowadząc core_sim od 0,9615 do zera.

E2 i E3 razem definiują charakter systemu: **odporność na nieciągłe ataki, adaptacyjność do ciągłego dryftu środowiskowego.** Identyfikujemy tę kombinację jako *reprezentację zależną od obserwatora* — atraktor koduje aktualny geometryczny pogląd systemu na dane wejściowe, nie stałą prawdę obiektywną. Precyzyjnie określamy to jako **percepcję bez kognicji**: system filtruje i selekcjonuje, ale nie generuje. Ścieżka do generacji (Genesis 6) wymaga, aby ślad produkował kandydatów do strumienia, zamykając pętlę w odwrotnym kierunku.

---

## 1. Motywacja

KarmazynMatrix v3.4 ustanowił zamknięty, wsadowy system: ustalona populacja atomów ewoluuje pod wpływem dynamiki temperatury aż do stabilizacji atraktora. Żadne nowe atomy nie wchodzą; żadne nie wychodzą z założenia. Jest to użyteczne do charakteryzacji dynamiki, ale nie jest to model systemu istniejącego w czasie i wchodzącego w interakcje z bieżącym środowiskiem.

System percepcyjny musi robić trzy rzeczy, które robi jego środowisko: odbierać nowe informacje ciągłe, zapominać stare informacje, które nie są już istotne, oraz utrzymywać spójną reprezentację aktualnego stanu. Genesis 5 dodaje dokładnie te trzy możliwości do KarmazynMatrix przy minimalnej zmianie architektonicznej:

- **Iniekcja strumienia** — atomy przybywają z zewnątrz z ustaloną częstotliwością na epokę.
- **Skończony czas życia** — atomy wygasają po `max_age` epokach niezależnie od temperatury.
- **Brama** — warunek przeżycia (`k·sim > λτ + f`) jest stosowany przy wejściu, nie tylko przy śmierci.

Rezultatem jest **żyjący atraktor**: ciągle odświeżany, ograniczony populacyjnie i responsywny na środowisko. Pytanie brzmi, czy ta responsywność jest kontrolowana (odporność na szum, stabilność pod atakiem) czy niekontrolowana (ślad przejęty przez cokolwiek nadchodzi). Odpowiedź, ustalona empirycznie, zależy krytycznie od *typu* zmiany środowiskowej.

---

## 2. Architektura

### 2.1 Struktura Pętli

Pętla generatywna wykonuje następującą sekwencję każdą epokę:

```
1. Wygasanie:  usuń atomy z wiekiem ≥ max_age (poza stałym rdzeniem)
2. Strumień:   pobierz stream_rate kandydatów z zewnętrznego rozkładu
3. Brama:      dopuść jeśli sim(kandydat, Trace) > gate_threshold
4. Wiek++:     zwiększ licznik wieku dla wszystkich przeżywających atomów
5. Krok KM:    zanik → rezonans → vacuum → przebudowa Trace
```

### 2.2 Próg Bramy

Próg bramy pochodzi z warunku przeżycia ustalonego w KarmazynMatrix v3.4:

```
gate_threshold = (λ·τ + f) / k = (0,08 · 0,15 + 0,01875) / 0,2 = 0,1537
```

To nie jest wolny parametr — jest to minimalne podobieństwo cosinusowe wymagane, aby atom przeżył na granicy próżni. Użycie tego samego progu dla wejścia tworzy architektoniczną spójność: kandydat, który nie może ostatecznie przeżyć dynamiki, nie może wejść. Brama jest predykcyjnym filtrem, nie twardym klasyfikatorem.

### 2.3 Równowaga Populacyjna

Przy skończonym czasie życia populacja w stanie stacjonarnym spełnia:

```
N_eq ≈ stream_rate × p_admitted × max_age + N_permanentne
```

Dla stream_rate=3, p_admitted≈0,3, max_age=30, N_permanentne=3: N_eq ≈ 12–30, zgodne z empirycznym 27,5.

### 2.4 Model Strumienia

Zewnętrzny strumień jest mieszaniną sygnału i szumu:

- **Atomy sygnałowe:** pobrane blisko centroidu (szum sygnału ε=0,4, więc sim(sygnał, centroid) ≈ 0,92).
- **Atomy szumowe:** czyste losowe wektory jednostkowe w R⁴⁰⁹⁶ (oczekiwane sim z dowolnym stałym wektorem ≈ 1/√4096 ≈ 0,016, daleko poniżej progu bramy).

| Parametr | Wartość | Źródło |
|---|---|---|
| Wymiar d | 4096 | KarmazynMatrix v3.4 |
| Próg bramy | 0,1537 | warunek przeżycia (λτ+f)/k |
| Częstość strumienia | 3/epokę | — |
| Maks. wiek atomu | 30 epok | N_eq ≈ 27 atomów |
| Frakcja sygnału p | 0,30 | 30% strumienia wyrównane z rdzeniem |
| Szum sygnału ε | 0,40 | sim(sygnał, centroid) ≈ 0,92 |
| Stałe atomy rdzenia | 3 | miłość, uczciwość, szacunek |

*Tabela 1. Parametry Genesis 5.*

---

## 3. Eksperymenty

### 3.1 E1 — Stabilność Populacji i Śladu

**Konfiguracja:** Rdzeń zaszczepiony i stabilizowany przez 20 epok. Strumień otwarty z p_signal=0,3, stream_rate=3, max_age=30. Uruchomiony przez 200 epok. Metryki zebrane od epoki 50 (po transjentnej fazie).

**Wyniki:**

| Metryka | Wartość | Interpretacja |
|---|---|---|
| Populacja (epoki 50–200) | 27,5 ± 3,66 | ograniczona, nie rośnie |
| Core sim (średnia) | 0,9586 ± 0,0003 | integralność śladu utrzymana |
| Dryft śladu na epokę | 0,000184 | quasi-statyczny, nie zamrożony |
| Próg bramy | 0,1537 | identyczny z warunkiem przeżycia |

*Tabela 2. Metryki stabilności E1.*

| Epoka | Pop | Core sim | Wpuszczone | Dryft |
|---|---|---|---|---|
| 21 (przed strumieniem) | 3 | 0,9615 | 0 | 0,001813 |
| 61 | 27 | 0,9586 | 0 | 0,000254 |
| 101 | 21 | 0,9578 | 1 | 0,000347 |
| 141 | 31 | 0,9588 | 1 | 0,000263 |
| 181 | 30 | 0,9589 | 2 | 0,000259 |

*Tabela 3. Trajektoria E1.*

Ślad nie jest zamrożony: dryft 0,000184/epokę oznacza, że kierunek atraktora powoli ewoluuje wraz z rotacją atomów strumienia. Jest to oczekiwane i pożądane — system utrzymuje żywą reprezentację, nie statyczną migawkę.

---

### 3.2 E2 — Odporność Ontologiczna

**Konfiguracja:** Po 100 przyjaznych epokach (p_signal=0,3, centroid strumienia wyrównany z rdzeniem), centroid strumienia jest przełączany na wektor ortogonalny do atraktora rdzenia. Frakcja sygnału wzrasta do p_signal=0,8 — wrogi strumień jest dominujący i trwały.

**Wyniki:**

| Metryka | Faza przyjazna | Faza wroga |
|---|---|---|
| Core sim (średnia) | 0,9583 | 0,9602 |
| Atomy wpuszczone | ~45 total | **0** |
| Końcowa populacja | ~25 | 3 (tylko stały rdzeń) |
| Brama naruszona | — | **NIE** |

*Tabela 4. Wyniki E2.*

| Epoka | Pop | Core sim | Wpuszczone | Faza |
|---|---|---|---|---|
| 96 (ostatnia przyjazna) | 21 | 0,9579 | 0 | przyjazna |
| 121 | 27 | 0,9586 | 0 | wroga |
| 146 | 8 | 0,9549 | 0 | wroga |
| 171 | 3 | 0,9615 | 0 | wroga |
| 196 | 3 | 0,9615 | 0 | wroga |

*Tabela 5. Trajektoria E2. Populacja starzeje się do minimum; core sim odzyskuje 0,9615.*

**Mechanizm:** wrogi centroid jest ortogonalny do aktualnego śladu. Jego atomy sygnałowe mają sim(S, Trace) ≈ 0 << gate_threshold = 0,1537. Brama blokuje bezwarunkowo. Gdy atomy strumienia z fazy przyjaznej wygasają przez ~30 epok, populacja spada do 3 (stały rdzeń). Ślad, nie rozcieńczony już atomami strumienia, wraca dokładnie do atraktora rdzenia (0,9615).

> **Wniosek E2:** Wroga presja nie degraduje rdzenia — oczyszcza go.

---

### 3.3 E3 — Stopniowy Dryft i Adaptacja

**Konfiguracja:** Centroid strumienia obraca się liniowo od wyrównania z rdzeniem do prostopadłości przez 100 epok, następnie utrzymuje się prostopadle przez kolejne 50 epok. Frakcja sygnału p_signal=0,3 przez cały czas. Metryka: core_sim(t) śledzi wyrównanie śladu z oryginalnymi wektorami stałego rdzenia.

**Wyniki:**

| Epoka | Pop | Core sim | Strumień→core sim | Reżim |
|---|---|---|---|---|
| 21 (początek) | 3 | 0,9615 | 1,0000 | wyrównany |
| 51 | 27 | 0,9531 | 0,9539 | wyrównany |
| 66 | 29 | 0,9263 | 0,8930 | wyrównany |
| 81 | 28 | 0,8842 | 0,8000 | dryfujący |
| 96 | 21 | 0,8187 | 0,6614 | dryfujący |
| 111 | 23 | 0,6852 | 0,4359 | dryfujący |
| 126 | 32 | 0,4073 | 0,0000 | prostopadły |
| 141 | 31 | 0,1558 | 0,0000 | prostopadły |
| 156 | 20 | −0,0004 | 0,0000 | prostopadły |

*Tabela 6. Trajektoria E3. Core sim maleje w lockstepie z obrotem strumienia.*

| Metryka | Wartość |
|---|---|
| Początkowy core sim | 0,9615 |
| Końcowy core sim | 0,0001 |
| Korelacja strumień–ślad | **0,9457** |
| Charakter systemu | **ADAPTACYJNY** |

*Tabela 7. Podsumowanie E3.*

**Mechanizm:** gdy centroid strumienia obraca się, ciągle wpuszcza atomy w nowym kierunku. Atomy te zyskują rezonans ze śladu (który nadal częściowo pokrywa się z nowym kierunkiem), przeżywają i stopniowo ciągną ślad. Stałe atomy rdzenia opierają się, ale są przeważone liczebnie przez rosnącą populację strumienia. Atraktor rdzenia jest nadpisywany przez około 80 epok.

> **Wniosek E3:** System nie jest stałym klasyfikatorem. Jest projekcją geometryczną aktualnego środowiska.

---

## 4. Interpretacja Naukowa

### 4.1 Kluczowa Asymetria

E2 i E3 nie są sprzeczne — ujawniają precyzyjną asymetrię w odpowiedzi systemu na zmianę środowiskową:

| Typ zmiany | Przejście strumienia | Odpowiedź bramy | Odpowiedź śladu | Skala czasu |
|---|---|---|---|---|
| Nieciągła (E2) | Rdzeń → ortogonalny (nagły) | Blokuje 100% | Powraca do czystego rdzenia | ~30 epok (max_age) |
| Ciągła (E3) | Rdzeń → ortogonalny (stopniowy) | Otwiera stopniowo | Podąża za dryftem do ortogonalności | ~80 epok |

*Tabela 8. Asymetria między nagłą a stopniową zmianą definiuje perceptualny charakter systemu.*

**Wyjaśnienie geometryczne:** W E2 nagłe przełączenie oznacza, że nowy centroid strumienia jest natychmiast ortogonalny do aktualnego śladu. Brama odpala za każdym razem: sim(sygnał_wrogi, ślad) ≈ 0 << 0,1537. Nic nie wchodzi. W E3 centroid strumienia jest zawsze bliski aktualnemu kierunkowi śladu (obraca się powoli). Każdą epokę część atomów strumienia jest wpuszczana, nieznacznie przesuwają ślad, a brama re-centruje wokół nowego śladu. System podąża za dryftem, bo brama jest definiowana względem *aktualnego stanu*, nie stanu początkowego.

### 4.2 Reprezentacja Zależna od Obserwatora

Wynik E3 jest kluczowym odkryciem naukowym. Różne warunki początkowe (lub różne historie środowiskowe) produkują różne atraktory z tego samego strumienia wejściowego. Dwie instancje Genesis 5 z identycznymi parametrami, ale różnymi zaszczepionymi rdzeniami, rozwiną ortogonalne ślady ze strumieni różniących się tylko wyrównaniem z tymi rdzeniami.

Ślad nie jest obiektywną reprezentacją strumienia — jest geometryczną projekcją strumienia na aktualną podprzestrzeń atraktora.

> **Trace = warunkowy widok rzeczywistości**

Warunkiem jest aktualny atraktor, który sam jest produktem historii. Nie istnieje obiektywna reprezentacja — tylko reprezentacja względem aktualnego stanu systemu.

Ta właściwość jest niebanalna w kontekście systemów VSA. Standardowa superpozycja HRR jest niezależna od obserwatora: te same wektory produkują ten sam ślad niezależnie od historii. Dynamika temperatury przekształca to w projekcję zależną od historii i atraktora.

### 4.3 Co Ten System Jest i Czym Nie Jest

| Zdolność | Status | Dowód |
|---|---|---|
| Równowaga populacyjna | ✓ zademonstrowana | E1: 27,5 ± 3,66 atomów |
| Integralność śladu | ✓ zademonstrowana | E1: core_sim 0,9586 ± 0,0003 |
| Odporność na nagły atak | ✓ zademonstrowana | E2: 0 wrogich atomów wpuszczonych |
| Adaptacja do ciągłego dryftu | ✓ zademonstrowana | E3: korelacja 0,9457 |
| Atraktor zależny od obserwatora | ✓ zademonstrowany | E3: ślad podąża za historią |
| Odrzucenie szumu ze strumienia | ✓ zademonstrowane | Brama: 0% losowych wpuszczonych |
| **Generacja nowego znaczenia** | **✗ nieobecna** | ślad nie tworzy kandydatów |
| Samozwrotna produkcja | ✗ nieobecna | pętla jest otwarta: strumień jest zewnętrzny |
| Kognicja / planowanie | ✗ nieobecna | brak wewnętrznej generacji |

*Tabela 9. Inwentarz zdolności Genesis 5.*

Genesis 5 jest warstwą percepcyjną. Odbiera, filtruje i reprezentuje. Nie generuje. Rozróżnienie między tymi dwoma funkcjami jest centralnym otwartym problemem dla Genesis 6.

---

## 5. Dyskusja

### 5.1 Relacja do Autopoiesis

Systemy autopoietyczne (Maturana i Varela, 1980) są definiowane przez zdolność do produkcji i utrzymywania składników, które je konstytuują. Genesis 5 spełnia pierwsze kryterium — populacja jest ciągle odnawiana przez strumień — ale nie drugie. Składniki (atomy strumienia) są produkowane zewnętrznie. System nie tworzy własnych atomów; tylko je selekcjonuje.

Genesis 6 zamknąłby tę lukę, czyniąc ślad odpowiedzialnym za generowanie kandydatów, którzy ponownie wchodzą do strumienia. W tym momencie system produkuje wejścia, które go podtrzymują. Czy taki system byłby stabilny, czy dryfowałby w degenerację (wszystkie samogenerowane atomy są identyczne ze śladem), jest głównym pytaniem teoretycznym.

### 5.2 Asymetria Odporność–Adaptacja jako Zasada Projektowania

Asymetria ustalona w sekcji 4.1 ma praktyczne implikacje: system można uczynić bardziej lub mniej adaptacyjnym przez regulację `max_age`.

- **Krótszy `max_age`** → szybsza rotacja → ślad adaptuje się szybciej do dryftu, ale jest też bardziej podatny na powolne ataki.
- **Dłuższy `max_age`** → wolniejsza rotacja → bardziej odporny na dryft, ale też na uzasadnione zmiany środowiskowe.

Jest to autentyczny kompromis, analogiczny do dylematu stabilność–plastyczność w uczeniu sieci neuronowych. Aktualna wartość (max_age=30) nie była optymalizowana; systematyczny przegląd max_age względem stopnia adaptacji i progu odporności byłby konkretnym następnym eksperymentem.

### 5.3 Relacja do Zasady Wolnej Energii

Zasada Wolnej Energii Fristona (2010) ujmuje percepcję jako minimalizację zaskoczenia — rozbieżności między generatywnym modelem systemu a przychodzącymi danymi sensorycznymi. Genesis 5 implementuje twardą wersję tego: atomy przekraczające próg zaskoczenia (sim < brama) są po prostu odrzucane, zamiast być używane do aktualizacji modelu generatywnego. Brama jest binarnym filtrem zaskoczenia, nie gradientem.

Miękka wersja — gdzie odrzucone atomy produkują mały sygnał aktualizacyjny — byłaby bliższa FEP i mogłaby pozwolić systemowi adaptować się do stopniowego dryftu, opierając się jednocześnie nieciągłym atakom. Jest to bezpośrednia ścieżka implementacji dla Genesis 6.

---

## 6. Ograniczenia

| Problem | Status |
|---|---|
| max_age nie zoptymalizowane względem kompromisu adaptacja/odporność | OTWARTE |
| Model strumienia jest syntetyczny | CZĘŚCIOWE |
| Brak analizy wieloseedowej przejścia E3 | OGRANICZONE |
| Interakcja skali czasowej stopniowego dryftu z max_age | OTWARTE |
| Genesis 6 (zamknięcie generatywne) nie zaimplementowane | OTWARTE — następny artykuł |

*Tabela 10. Otwarte problemy.*

---

## 7. Ścieżka do Genesis 6

Genesis 6 wymaga zamknięcia pętli w odwrotnym kierunku: Trace → nowi kandydaci do strumienia → ponowne wejście do systemu. Minimalna implementacja:

```python
new_candidate = normalize(Trace + ε · noise + δ · random_walk)
T_init = k · sim(new_candidate, Trace) / λ   # proporcjonalne do wyrównania
```

Trzy pytania muszą zostać odpowiedziane przed nazwaniem tego generacją zamiast amplifikacji:

1. **Degeneracja:** czy samogenerowany strumień zbiega do punktu stałego (wszyscy kandydaci identyczni ze śladem), i jeśli tak, to w jakich warunkach?

2. **Nowość:** czy samogeneracja może produkować kandydatów poza aktualną podprzestrzenią atraktora? Jeśli T_init jest proporcjonalne do sim, przeżywają tylko kandydaci bliskie śladu — system nie może eksplorować.

3. **Kompromis stabilność–kreatywność:** czysty zewnętrzny strumień (Genesis 5) jest stabilny, ale nie generatywny. Czysty samozwrotny strumień byłby generatywny, ale potencjalnie niestabilny. Proporcja mieszania jest kluczowym parametrem sterującym.

Ścieżka do kognicji wymaga odpowiedzi na pytanie 2: jak system generuje kandydatów, którzy są *nowi* względem jego aktualnego stanu, a jednocześnie wystarczająco spójni, aby przeżyć bramę? To jest minimalna definicja kreatywnej percepcji i nie jest jeszcze rozwiązana.

---

## 8. Wnioski

Genesis 5 dodaje minimalną pętlę generatywną do KarmazynMatrix: zewnętrzny strumień filtrowany przez ten sam geometryczny próg, który rządzi wewnętrznym przeżyciem. Trzy odkrycia:

1. Równowaga populacyjna jest osiągana i utrzymywana (27,5 ± 3,66 atomów, ograniczona). Integralność śladu utrzymuje się na poziomie core_sim = 0,9586 ± 0,0003 przez ciągłą pracę.

2. Nieciągłe wrogie strumienie są całkowicie blokowane (0 wpuszczonych). Gdy faza wroga postępuje, system oczyszcza się do stałego rdzenia, a jakość śladu poprawia się. Nieciągłe ataki są odpierane bezwarunkowo.

3. Ciągły dryft środowiskowy jest śledzony. Obrót strumienia od wyrównania z rdzeniem do prostopadłości przez 100 epok prowadzi korelację śladu do 0,9457 ze strumieniem, a core_sim od 0,9615 do 0,0001. Atraktor nie jest stały — jest aktualnym geometrycznym poglądem systemu na jego środowisko.

Kombinacja odporności (E2) i adaptacji (E3) definiuje system jako mechanizm reprezentacji zależnej od obserwatora — warstwę percepcyjną, która utrzymuje spójność przeciwko szumowi, pozostając otwartą na autentyczną zmianę środowiskową. **To jest percepcja bez kognicji.** Generacja wymaga zamknięcia pętli w odwrót: ślad musi produkować kandydatów, których filtruje. To jest Genesis 6.

---

## Referencje

[1] Kanerva, P. (2009). Hyperdimensional computing. *Cognitive Computation*, 1(2), 139–159.

[2] Plate, T.A. (1995). Holographic reduced representations. *IEEE Trans. Neural Networks*, 6(3), 623–641.

[3] Maturana, H.R., Varela, F.J. (1980). *Autopoiesis and Cognition*. Reidel, Dordrecht.

[4] Friston, K. (2010). The free-energy principle: a unified brain theory? *Nature Reviews Neuroscience*, 11(2), 127–138.

[5] Taylor, P.D., Jonker, L.B. (1978). Evolutionary stable strategies and game dynamics. *Mathematical Biosciences*, 40(1–2), 145–156.

[6] Mazur, M. (2026). KarmazynMatrix v3.4: Temperature-Gated Mean-Field Attractor Dynamics. Preprint.

---

*Kod: `genesis5.py` (wymaga `karmazyn_matrix_v34.py`). Uruchom `python genesis5.py` aby odtworzyć wszystkie wyniki.*
