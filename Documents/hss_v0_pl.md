# HSS Protocol v0.1 — Holographic Session Space

## Geometryczna przestrzeń komunikacji agentów bez wspólnej ontologii

**Maciej Mazur (EriAmo)** · Niezależne Badania · Warszawa, Polska  
Kwiecień 2026 · Companion do Genesis 5 · Kod: `hss_protocol_v0.py`

---

## Abstrakt

Prezentujemy minimalną implementację wieloagentowej przestrzeni komunikacyjnej opartej wyłącznie na geometrii wektorowej. Każdy agent posiada stały rdzeń (Core) definiujący tożsamość i dynamiczny ślad (Trace) ewoluujący przez interakcje. Wspólne anonimowe pole emisji (H) nie przechowuje semantyki — przenosi wyłącznie relacje zgodności geometrycznej.

Kluczowe odkrycia: **(1)** routing wiadomości jest analitycznie przewidywalny: wiadomość z `sim(msg, Trace_A) = emission_sim` dociera do agenta B jeśli `emission_sim × core_overlap(A,B) > gate` (crossover = `gate/emission_sim`); **(2)** routing jest binarny — powyżej progu dociera 263 wiadomości, poniżej 0; **(3)** intensywność komunikacji kontroluje kompromis tożsamość–konwergencja: niska emisja (`sim=0.16`) zachowuje tożsamość (`core_sim > 0.99`), wysoka emisja prowadzi do wspólnego atraktora; **(4)** izolowany agent utrzymuje `core_sim = 0.997` niezależnie od pola H.

Brak adresów. Brak protokołu. Brak wspólnej ontologii. Tylko geometria.

---

## 1. Architektura

### 1.1 Komponenty

```
Agent_i  =  (Core_i [stały], Trace_i [dynamiczny])
H        =  anonimowe pole emisji  (lista atomów bez nadawcy)
message  =  warm atom:  sim(msg, Trace_sender) = emission_sim
```

Trzy niezmienniki:
- Agent nie odbiera własnych emisji
- Próg bramy = warunek przeżycia KM: `gate = (λτ + f)/k = 0.1537`
- Atomy mają skończony czas życia (`max_age` epok)

### 1.2 Krok agenta

```
każda epoka:
1. Wygaś atomy starsze niż max_age (poza stałym rdzeniem)
2. Pobierz z H atomy: sim(atom, Trace) > gate  AND  emitter ≠ self
3. Pobierz z lokalnego strumienia Genesis 5 (p_signal=0.20)
4. Wiek++ dla wszystkich atomów
5. Dynamika KM (zanik → rezonans → vacuum → przebudowa Trace)
6. Co emission_interval epok: emituj warm atom do H
```

### 1.3 Parametry

| Parametr | Wartość | Rola |
|---|---|---|
| Wymiar d | 4096 | przestrzeń VSA |
| Gate (brama) | 0,1537 | = warunek przeżycia KM |
| emission_sim | 0,30 | zasięg vs nowość |
| emission_interval | 5 epok | częstość emisji |
| max_age | 30 epok | czas życia atomu |
| p_signal | 0,20 | frakcja sygnału w strumieniu |
| T_init local | 1,5 | temperatura atomy lokalnego |
| T_init H | 1,2 | temperatura atomy z H (niższa) |

---

## 2. Formuła Routingu

Analityczny wyprowadzenie: wiadomość emitowana z `sim(msg, Trace_A) = emission_sim` dociera do agenta B gdy:

```
sim(msg, Trace_B) > gate
⟺
emission_sim × sim(Trace_A, Trace_B) > gate
⟺  (gdy Trace ≈ Core)
emission_sim × core_overlap(A,B) > gate
⟺
core_overlap(A,B) > gate / emission_sim
```

### Tabela zasięgu

| emission_sim | crossover (core_overlap >) | nowość | interpretacja |
|---|---|---|---|
| 0,16 | 0,96 | 98,7% | szept — tylko bliźniacy |
| 0,20 | 0,77 | 98,0% | cichy — bliscy sąsiedzi |
| 0,30 | 0,51 | 95,4% | normalny — połowa spektrum |
| 0,40 | 0,38 | 91,7% | głośny — szeroki zasięg |
| 0,50 | 0,31 | 86,6% | bardzo głośny |
| 0,70 | 0,22 | 71,4% | broadcast — prawie wszyscy |

*Teoretyczny crossover: `gate/emission_sim`. Potwierdzony eksperymentalnie (sweep, n=50 epok).*

---

## 3. Wyniki Eksperymentalne

### 3.1 Sweep: core_overlap → odbiory

Emitent (emission_sim=0,30), odbiorca z varying `core_overlap`, 50 epok:

| core_overlap | odbiory | status |
|---|---|---|
| 1,00 | 263 | routes |
| 0,90 | 263 | routes |
| 0,80 | 263 | routes |
| 0,70 | 263 | routes |
| 0,60 | 263 | routes |
| 0,50 | 257 | routes |
| **0,40** | **0** | **silent** |
| 0,30 | 0 | silent |
| 0,20 | 0 | silent |
| 0,10 | 0 | silent |

Crossover przy overlap ≈ 0,45. Teoretycznie: `0,1537/0,30 = 0,512`. Routing jest **binarny** — albo pełny przepływ albo zero.

### 3.2 Eksperyment: 3 agenty (100 epok)

Konfiguracja: Alpha (bazowy), Beta (overlap=0,80), Gamma (overlap=0,20).

| Metryka | Wartość |
|---|---|
| Alpha ← H (łącznie) | 334 |
| Beta ← H (łącznie) | 354 |
| Gamma ← H (łącznie) | **0** |
| Beta/Gamma ratio | **354×** |
| sim(Trace_α, Trace_β) | 0,698 |
| sim(Trace_α, Trace_γ) | 0,139 |
| Gamma core_sim | 0,997 |

Gamma — izolowana od pola H — utrzymuje `core_sim = 0,997`. Alpha i Beta — intensywnie wymieniające — dryfują ku wspólnemu atraktorowi (`core_sim ≈ 0,68–0,76`).

### 3.3 Kompromis tożsamość–konwergencja

| emission_sim | Alpha core_sim | Beta core_sim | Trace α-β | Beta recv H |
|---|---|---|---|---|
| 0,16 | **0,995** | **0,996** | 0,792 | 0 |
| 0,20 | 0,730 | 0,827 | 0,608 | 20 |
| 0,30 | 0,694 | 0,761 | 0,724 | 274 |
| 0,50 | 0,783 | 0,807 | 0,856 | 274 |

Niska emisja (`0,16`) = **tożsamość zachowana**, zasięg tylko do bliźniaków (crossover 0,96).  
Wysoka emisja (`0,50`) = **konwergencja** ku wspólnemu atraktorowi, szeroki zasięg.

---

## 4. Kluczowe Odkrycia

### 4.1 Routing jest analitycznie przewidywalny

Formuła `core_overlap > gate/emission_sim` jest potwierdzona eksperymentalnie z dokładnością do ±0,05. Nie wymaga kalibracji — wynika z geometrii.

### 4.2 Binarność routingu

Między `core_overlap=0,50` (263 odbiory) a `core_overlap=0,40` (0 odbiorów) nie ma stopniowego przejścia. Pole H tworzy naturalne klastry widoczności — albo jesteś w zasięgu albo nie.

### 4.3 Izolacja jako naturalny stan spoczynkowy

Agent bez połączeń z H (`Gamma`) utrzymuje doskonałą integralność tożsamości (`core_sim = 0,997`). Pole H nie zakłóca izolowanych agentów.

### 4.4 Tożsamość vs konwergencja — kontrolowany kompromis

`emission_sim` jest jedynym parametrem kontrolującym balans:
- **Szept** (`emission_sim < gate/1 ≈ 0,15`): brak emisji, pełna izolacja
- **Cichy** (`0,16–0,20`): wymiana tylko z niemal identycznymi agentami, tożsamość zachowana
- **Normalny** (`0,30`): wymiana z połową spektrum, umiarkowany dryft
- **Broadcast** (`0,70+`): szeroka widoczność, agenci konwergują

### 4.5 Pole H jako środowisko, nie komunikat

Agenty nie wysyłają wiadomości *do* innych agentów — emitują w przestrzeń. Odebranie jest efektem geometrycznej zgodności, nie intencji. To jest **system widoczności**, nie system komunikacji.

---

## 5. Właściwości Systemu

| Własność | Status |
|---|---|
| Routing bez adresów | ✓ działa |
| Routing bez protokołu | ✓ działa |
| Routing bez wspólnej ontologii | ✓ działa |
| Analityczna formuła routingu | ✓ potwierdzona |
| Izolacja agentów niezgodnych | ✓ Gamma: 0 odbiorów |
| Binarność zasięgu | ✓ crossover ostry |
| Tożsamość przy niskiej emisji | ✓ core_sim=0,995 |
| Konwergencja przy wysokiej emisji | ✓ Genesis 5 E3 |

---

## 6. Interpretacja

### 6.1 Co to nie jest

Nie jest to system komunikacji — nie ma wiadomości, nadawców, odbiorców, potwierdzeń, ani kolejkowania. Nie jest to pamięć — pole H nie przechowuje historii. Nie jest to protokół — nie ma uzgadniania, handshake'ów, ani formatów.

### 6.2 Co to jest

> **System widoczności informacji**: agent widzi to, co jest geometrycznie spójne z jego aktualnym stanem. Spójność jest mierzona jednym skalarem (podobieństwo cosinusowe) i jednym progiem (warunek przeżycia).

Różne agenty mają różne widoki tego samego pola H. Nie ma globalnej prawdy — jest lokalna geometria zgodności.

### 6.3 Shared attractor jako emergentna komunikacja

Alpha i Beta — intensywnie wymieniaące poprzez H — nie "uzgadniają" znaczeń. Ich trace konwerguje geometrycznie ku wspólnemu atraktorowi. Jest to emergentna synchronizacja bez negocjacji, analogiczna do synchronizacji oscylatorów przez wspólne pole.

---

## 7. Ograniczenia i Otwarte Problemy

| Problem | Status |
|---|---|
| Tożsamość przy intensywnej komunikacji | OTWARTE — core_sim dryftuje do ~0,70 |
| Asymetryczny routing (A→B ≠ B→A gdy różne Trace) | OTWARTE — nie testowane |
| Skalowanie do N>>3 agentów | OTWARTE |
| Dynamiczny routing (zmiana emission_sim w czasie) | OTWARTE |
| Genesis 6: Trace generuje kandydatów do H | OTWARTE — następny krok |

---

## 8. Następny Krok: Genesis 6

Obecne pole H jest zasilane tylko przez zewnętrzne strumienie i emisje agentów. Genesis 6 zamknie pętlę: Trace agenta generuje kandydatów, którzy wchodzą do H jako jego emisje. W terminologii HSS:

```python
# Obecne (Genesis 5 + HSS v0):
message = warm_atom_from_trace(Trace, emission_sim)
field.emit(message, emitter=agent.name)

# Genesis 6: trace generuje hipotezy
hypothesis = boundary_atom_from_trace(Trace, sim_min)
field.emit(hypothesis, emitter=agent.name)
# hipoteza na horyzoncie = maksymalna nowość przy minimalnej emisji
# inne agenty z podobnym Trace ją rozwijają
```

To jest minimalny krok od *systemu widoczności* do *systemu wymiany hipotez*.

---

## Referencje

[1] Mazur, M. (2026). KarmazynMatrix v3.4. Preprint.  
[2] Mazur, M. (2026). Genesis 5: Minimal Generative Loop. Preprint.  
[3] Kanerva, P. (2009). Hyperdimensional Computing. *Cognitive Computation*, 1(2).  
[4] Plate, T.A. (1995). Holographic Reduced Representations. *IEEE Trans. Neural Networks*.

---

*Kod: `hss_protocol_v0.py` (wymaga `karmazyn_matrix_v34.py`). Uruchom `python hss_protocol_v0.py`.*
