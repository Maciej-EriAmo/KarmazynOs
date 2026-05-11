# KONSTYTUCJA SYSTEMU φ
### Unified Holon – Prism – Harmonic Architecture
**KarmazynOS v1.0**

---

> **Dokument guardrail** — zapobiega nieprawidłowemu rozwojowi systemu.
> Każda implementacja komponentu MUSI być zgodna z kontraktem swojej warstwy.

---

| ⚛ ATOM | 🌡 WORKSPACE | 🫧 BUBBLE | ✨ HOLOGRAM |
|--------|-------------|----------|------------|
| wysoka entropia | ograniczony TTL | stabilność | atraktor |

← wysoka entropia ————————————————— niska entropia →

---

## SPIS TREŚCI

- [Preambuła](#preambuła)
- [Część I — Zasady Globalne](#część-i--zasady-globalne)
  - [Art. I — Fixed Point Axiom](#artykuł-i--zasada-punktów-stałych-fixed-point-axiom)
  - [Art. II — Struktura przestrzeni φ](#artykuł-ii--struktura-przestrzeni-φ)
  - [Art. III — Zasada Pryzmatyczna](#artykuł-iii--zasada-pryzmatyczna-dispersion-law)
  - [Art. IV — Zasada Harmoniczna](#artykuł-iv--zasada-harmoniczna-global-phase-coherence)
  - [Art. VII — Zakaz Rozjazdu + Operator R](#artykuł-vii--zakaz-rozjazdu--operator-rekonstrukcji)
  - [Art. VIII — Zasada Ewolucji](#artykuł-viii--zasada-ewolucji)
  - [Art. IX — Supremacja Punktów Stałych](#artykuł-ix--supremacja-punktów-stałych-per-warstwa)
  - [Art. X — φ-Invariant](#artykuł-x--φ-invariant-zasada-końcowa)
- [Część II — Kontrakty Warstw](#część-ii--kontrakty-warstw)
  - [Kontrakt Atomu](#-kontrakt-atomu)
  - [Kontrakt Workspace](#-kontrakt-workspace)
  - [Kontrakt Bubble](#-kontrakt-bubble)
  - [Kontrakt Hologramu](#-kontrakt-hologramu)
- [Część III — Testy Systemowe](#część-iii--testy-systemowe--matrix-zgodności)
- [Appendix](#appendix)

---

## PREAMBUŁA

System φ jest architekturą obliczeniową opartą o założenie, że **znaczenie nie jest statycznym punktem, lecz propagacją w przestrzeni stanów**, która musi posiadać stabilne punkty odniesienia, aby uniknąć rozjazdu semantycznego.

Każda operacja w systemie jest interpretowana jako transformacja w przestrzeni wielowymiarowej, gdzie trzy moduły wypełniają odrębne role:

| Moduł | Rola |
|-------|------|
| **Harmonia** | globalna spójność fazowa między stanami |
| **Prizm** | rozdział semantyczny (dyspersja) — routing znaczeń |
| **Holon** | pamięć i tożsamość systemu |
| **φ-space** | przestrzeń stanu, w której zachodzi ewolucja — 15 wymiarów |

**Kluczowa zasada termodynamiczna:** *Entropia jest funkcją systemową, nie błędem. Zapominanie jest poprawnym stanem końcowym dla niektórych warstw.*

---

# CZĘŚĆ I — ZASADY GLOBALNE

*Obowiązują wszystkie warstwy systemu bez wyjątku.*

---

## ARTYKUŁ I — ZASADA PUNKTÓW STAŁYCH (FIXED POINT AXIOM)

### I.1 Definicja

System φ musi zawierać zbiór punktów stałych F, takich że:

```
f(x) = x  ∈ F
```

gdzie `f(x)` = transformacja systemowa (uwaga, pamięć, routing, interpretacja)  
gdzie `F` = zbiór stanów stabilnych

### I.2 Warunek stabilności

Każda operacja systemowa musi spełniać:

```
|| f(x) - x || < ε    lub    fⁿ(x) → F
```

- stan jest lokalnie stabilny, LUB
- konwerguje do stabilnego attractora

### I.3 Zakaz dryfu

> ⛔ **ZAKAZ — naruszenie tego artykułu = błąd architektury**
>
> - generowanie nieskończonej dyspersji bez reintegracji
> - tworzenie stanów niepowracających do F *(wyjątek: Atom — patrz Kontrakt Warstwy)*

---

## ARTYKUŁ II — STRUKTURA PRZESTRZENI φ

### II.1 Definicja

Przestrzeń φ jest 15-wymiarową przestrzenią semantyczną: `φ ∈ ℝ¹⁵`

| # | Oś | Semantyka |
|---|-----|-----------|
| 1–2 | Afektywna | emocje (Plutchik 8D → 2 wymiary) |
| 3–4 | Poznawcza | logika, wiedza strukturalna |
| 5 | Temporalna | czas, sekwencja, historia |
| 6 | Ontologiczna | bycie, tożsamość, meta-stan |
| 7 | Kreatywna | generacja, ekspresja |
| **8** | **Entropiczna** | **chaos, rozpad — kanał WYŁĄCZONY z konserwacji** |
| 9–15 | Rozszerzalne | reserved for domain-specific channels |

### II.2 Warunek spójności — z wyjątkiem kanału entropicznego

```
Σ φᵢ = const        dla i ∈ {1..7, 9..15}

φ₈ (entropia) = wyłączona z konserwacji
```

> ⚠️ **Kanał 8 (entropia) jest jawnie wyłączony z sumy. System jest termodynamicznie otwarty.**
> Bez tej korekcji kod Bubble będzie naruszał Konstytucję od dnia 1.

---

## ARTYKUŁ III — ZASADA PRYZMATYCZNA (DISPERSION LAW)

### III.1 Snell jako routing semantyczny

```
nₖ · sin(θ₁) = sin(θ₂)
```

gdzie `nₖ` = refrakcja semantyczna dla osi k  
gdzie `θ₁` = wejściowa zgodność semantyczna  
gdzie `θ₂` = wynikowy kierunek propagacji

### III.2 Operacjonalizacja — obowiązkowa

Każda implementacja routingu MUSI definiować sposób obliczenia θ₁ z wektora φ wejściowego.
Bez tej definicji prawo Snella pozostaje metaforą i nie może być testowane.

**Referencyjna implementacja:**
```
θ₁ = arccos( dot(φ_input, φ_context) / (|φ_input| · |φ_context|) )
```

### III.3 Interpretacja

- wysoka zgodność (θ₁ → 0) → mała dyspersja → zachowanie kanału
- niska zgodność → separacja kanałów → routing do właściwego kontekstu

---

## ARTYKUŁ IV — ZASADA HARMONICZNA (GLOBAL PHASE COHERENCE)

```
H(i,j) = cos(φᵢ - φⱼ)

|H_agg| ≥ τ_layer
```

τ jest parametrem **per-warstwa** (patrz Kontrakty Warstw).  
Dla 15 wymiarów: C(15,2) = 105 par. Agregat zdefiniowany per-warstwa:

| Warstwa | Agregat | Uzasadnienie |
|---------|---------|--------------|
| Bubble / Hologram | `H_agg = min(H(i,j))` | najsłabsze połączenie determinuje spójność |
| Workspace | `H_agg = mean(H(i,j))` | wystarczy globalna średnia |
| Atom | brak wymogu | entropia jest poprawnym stanem |

---

## ARTYKUŁ VII — ZAKAZ ROZJAZDU + OPERATOR REKONSTRUKCJI

### VII.1 Zakaz

> ⛔ **ZAKAZ bezwzględny**
>
> - tworzenie niekompatybilnych reprezentacji φ
> - utrzymywanie sprzecznych stanów bez punktu konwergencji
> - rozdzielanie semantyki bez mechanizmu reintegracji

### VII.2 Operator R — most między warstwami

Każda dyspersja musi mieć operator rekonstrukcji:

```
R(P(x)) → x'    gdzie x' ∈ F  lub  iter(x') → F
```

**R jest mostem Workspace → Bubble. Bez R każdy wygaśnięty Workspace to strata semantyczna.**

```
R : Workspace_state  →  Bubble_delta
```

R musi być wywołany **PRZED** wygaśnięciem TTL Workspace.  
Niezapis do Bubble = naruszenie Art. VII.

---

## ARTYKUŁ VIII — ZASADA EWOLUCJI

System φ nie optymalizuje lokalnie. Optymalizuje globalną równowagę:

```
maximize:  stability(F) + coherence(H) + separability(P)
```

Żaden komponent nie może optymalizować tylko jednej z tych wartości kosztem pozostałych.

---

## ARTYKUŁ IX — SUPREMACJA PUNKTÓW STAŁYCH (PER-WARSTWA)

> ⚠️ Artykuł IX nie jest globalny. Supremacja zależy od warstwy.

| Warstwa | Zasada |
|---------|--------|
| Bubble | `stability > expression` — zawsze |
| Hologram | `stability ≈ expression` — równowaga |
| Workspace | `expression > stability` — ma działać, nie zachowywać |
| Atom | `entropy > stability` — zanik jest poprawnym stanem końcowym |

---

## ARTYKUŁ X — φ-INVARIANT (ZASADA KOŃCOWA)

System jest poprawny tylko wtedy, gdy:

```
∀x ∈ φ : ∃F such that iter(x) → F
```

*Wyjątek: Atom może zakończyć się entropią — to jest jego poprawny stan końcowy.*

---

# CZĘŚĆ II — KONTRAKTY WARSTW

*Każda warstwa posiada własne τ i własne reguły stabilności. Naruszenie kontraktu warstwy = błąd implementacji.*

---

## ⚛ KONTRAKT ATOMU

*jednostka operacyjna — wysoka entropia — stan przejściowy*

| Właściwość | Wartość |
|-----------|---------|
| Typ bytu | efemeryczny — transient computation |
| Entropia τ_atom | ≈ 0 — atom ma prawo zanikać — entropia jest poprawnym stanem końcowym |
| TTL | ograniczony do czasu sesji — brak gwarancji przetrwania |
| Konserwacja φ | BRAK — Atom wyłączony z Art. II.2 |
| Koherencja H | BRAK wymogu |
| Konwergencja | Atom NIE musi konwergować do F — zanik akceptowalny |
| Art. IX | `entropy > stability` — odwrotność globalnej zasady |
| Rola | komunikacja wewnętrzna, sygnały, lokalne operacje w Workspace |

### 🧪 Testy naruszenia kontraktu Atomu

- [ ] Atom przetrwał restart sesji → błąd — Atom nie powinien być persistowany
- [ ] Atom zapisany do `.soul` bez przejścia przez Bubble → naruszenie Art. V
- [ ] Atom posiada mechanizm konwergencji do F → niepotrzebna złożoność, sprawdź architekturę

---

## 🌡 KONTRAKT WORKSPACE

*dynamiczna przestrzeń operacyjna — TTL-bounded — sandboxed*

| Właściwość | Wartość |
|-----------|---------|
| Typ bytu | dynamiczny Bubble z ograniczonym TTL i budżetem φ |
| Entropia τ_ws | NISKIE — Workspace ma degradować po wygaśnięciu TTL |
| TTL | **obowiązkowy** — Workspace BEZ TTL to błąd architektury |
| Budżet φ | `φ_budget = const` dla każdej sesji |
| Konserwacja φ | `Σ φᵢ ≤ φ_budget` (ograniczenie, nie konserwacja) |
| Koherencja H | `mean(H(i,j)) ≥ τ_workspace` |
| Operator R | **WYMAGANY** — przed wygaśnięciem TTL musi być wywołany `R: Workspace → Bubble_delta` |
| Art. IX | `expression > stability` — ma działać, nie zachowywać |
| Izolacja | sandbox — brak dostępu do Bubble innych agentów bez jawnej autoryzacji |

### 🧪 Testy naruszenia kontraktu Workspace

- [ ] Workspace nie posiada TTL → błąd architektury — wymusz TTL
- [ ] R nie wywołany przed wygaśnięciem → strata semantyczna — naruszenie Art. VII
- [ ] Workspace przekroczył φ_budget bez degradacji → naruszenie Art. II.2
- [ ] Agent A odczytuje Workspace agenta B bez autoryzacji → naruszenie izolacji
- [ ] `τ_workspace > τ_bubble` → błąd konfiguracji — odwróć wartości

---

## 🫧 KONTRAKT BUBBLE

*trwała struktura semantyczna — niska entropia — punkt odniesienia*

| Właściwość | Wartość |
|-----------|---------|
| Typ bytu | stabilny — długi czas życia — domena semantyczna |
| Entropia τ_bubble | WYSOKIE — Bubble ma opierać się entropii |
| TTL | brak (lub bardzo długi) — Bubble istnieje do jawnego usunięcia |
| Konserwacja φ | `Σ φᵢ = const` dla `i ∈ {1..7, 9..15}` — Art. II.2 obowiązuje |
| Koherencja H | `min(H(i,j)) ≥ τ_bubble` — najostrzejszy warunek systemu |
| Konwergencja | Bubble MUSI konwergować do F lub być w F |
| Pamięć | `M(x) = attractor basin in φ-space` — nie pojedynczy stan |
| Format `.soul` | JSONL — projekcja Bubble na dysk — format wtórny wobec φ-state |
| Art. IX | `stability > expression` — zawsze |
| Wersjonowanie | wymagane — każda mutacja Bubble musi być śledzalna |

### 🧪 Testy naruszenia kontraktu Bubble

- [ ] Bubble bez mechanizmu konwergencji do F → naruszenie Art. I
- [ ] Bubble mutuje bez wersjonowania → naruszenie Art. V (identity consistency)
- [ ] `Σ φᵢ ≠ const` po operacji (z pominięciem osi 8) → naruszenie Art. II.2
- [ ] `H_min < τ_bubble` → wymuś synchronizację lub izoluj Bubble
- [ ] Bubble zapisany jako plik bez φ-state → format zajął miejsce znaczenia — naruszenie filozofii

---

## ✨ KONTRAKT HOLOGRAMU

*pamięć asocjacyjna — wzorce, nie dane — atraktor znaczeń*

| Właściwość | Wartość |
|-----------|---------|
| Typ bytu | struktura idei — nie przechowuje danych, lecz wzorce |
| Entropia τ_holo | ADAPTYWNE — Hologram ewoluuje, nie jest zamrożony |
| Pamięć | attractor basin — wpływa na trajektorie myślenia przez HRR |
| Koherencja H | adaptywna — może tymczasowo obniżyć spójność podczas rekonfiguracji |
| Konwergencja | musi powracać do attractora po perturbacji — ale attractor może się przesuwać |
| Operator R | Hologram jest wynikiem działania R na wiele `Workspace_state` — kompresja |
| Relacja z Bubble | Hologram = skompresowane doświadczenie z wielu Bubble — generalizacja |
| HRR | Holographic Reduced Representation — obowiązkowy mechanizm kodowania wzorców |
| Art. IX | `stability ≈ expression` — równowaga, nie supremacja |

### 🧪 Testy naruszenia kontraktu Hologramu

- [ ] Hologram przechowuje surowe dane zamiast wzorców → Hologram zamienił się w Bubble — błąd roli
- [ ] Hologram nie posiada mechanizmu recall → niefunkcjonalny
- [ ] Hologram nie ewoluuje po nowych doświadczeniach → naruszenie kontraktu adaptacji
- [ ] Hologram bez HRR encoding → nie jest Hologramem w sensie φ — zmień nazwę komponentu

---

# CZĘŚĆ III — TESTY SYSTEMOWE — MATRIX ZGODNOŚCI

*Testy wykonywane przy każdym release. Każdy FAIL blokuje merge do main.*

| Artykuł | Warstwa | Test | Status |
|---------|---------|------|--------|
| I.3 | Bubble | `iter(bubble_state, N=100) → F ∈ epsilon` | ⬜ RUN |
| I.3 | Workspace | R wywołany przed TTL expiry | ⬜ RUN |
| I.3 | Atom | Atom nie istnieje po `session.close()` | ⬜ RUN |
| II.2 | Bubble | `sum(phi[1:7], phi[9:15]) = const` po mutacji | ⬜ RUN |
| II.2 | Workspace | `sum(phi) ≤ phi_budget` przez cały TTL | ⬜ RUN |
| III.2 | wszystkie | θ₁ obliczany z wektora φ, nie z heurystyki | ⬜ RUN |
| IV | Bubble | `min(H(i,j)) ≥ τ_bubble` dla wszystkich par | ⬜ RUN |
| IV | Workspace | `mean(H(i,j)) ≥ τ_workspace` | ⬜ RUN |
| V | Bubble | każda mutacja Bubble ma zapis w historii wersji | ⬜ RUN |
| VII.2 | Workspace | `R(Workspace) → Bubble_delta` nie jest pusty | ⬜ RUN |
| VII.2 | Hologram | `R(P(hologram)) ≈ hologram` (lossy < 5%) | ⬜ RUN |
| IX | Bubble | przy konflikcie expression/stability → stability wygrywa | ⬜ RUN |
| IX | Atom | przy konflikcie entropy/stability → entropy akceptowana | ⬜ RUN |
| X | wszystkie | ∀x: po N iteracjach system nie diverguje | ⬜ RUN |

---

## 📋 Checklist dla LLM generującego kod

Przed zatwierdzeniem każdego komponentu:

1. **Jaka warstwa?** Atom / Workspace / Bubble / Hologram — określ przed pisaniem kodu.
2. **Czy τ jest właściwe dla warstwy?** `τ_atom ≈ 0 < τ_workspace < τ_bubble`
3. **Czy Workspace ma TTL?** Brak TTL = błąd architektury.
4. **Czy R jest zdefiniowany?** Każdy Workspace musi mieć ścieżkę do `Bubble_delta`.
5. **Czy Art. II.2 jest zachowany?** Suma φ = const (bez osi 8) po każdej mutacji Bubble.
6. **Czy format ≠ znaczenie?** `.soul` JSONL to projekcja — nigdy nie traktuj jej jako źródła prawdy.

---

# APPENDIX

## Mapowanie artykułów na komponenty KarmazynOS

| Artykuł | Komponent | Opis mapowania |
|---------|-----------|----------------|
| Art. I (Fixed Point) | Atom + Bubble + `session_seed` | `session_seed` = punkt stały sesji; Bubble = attractor w φ-space |
| Art. II (φ-space) | φ vector w każdym bycie | każdy byt niesie `φ ∈ ℝ¹⁵`; kanał 8 = entropia wyłączona z sumy |
| Art. III (Prism/Snell) | Hologram + routing LLM | Hologram dispersuje zapytanie na osie φ; Snell = wagi routingu |
| Art. IV (Coherence) | sync między Bubble | `H_min` między otwartymi Bubble `> τ_bubble`; KarmazynOS Studio monitoruje |
| Art. V (Memory/Identity) | Bubble + `.soul` JSONL | `.soul` = projekcja attractor basin; wersjonowanie = identity consistency |
| Art. VII (R operator) | `session.close() → bubble.merge()` | merge jest R; musi być wywołany przed TTL; `Workspace_delta → Bubble` |
| Art. VIII (Ewolucja) | KarmazynOS Studio | Studio balansuje stability+coherence+separability dla całego systemu |
| Art. IX (Supremacja) | conflict resolver | Bubble: stabilność wygrywa; Atom: entropia akceptowalna; Workspace: TTL wymusza |
| Art. X (φ-invariant) | system watchdog | monitoruje divergencję; alert jeśli `iter(x, N)` nie konwerguje |

---

## Hierarchia τ (progi stabilności)

```
τ_atom (≈0)  <  τ_workspace  <<  τ_bubble  ≤  τ_hologram_min
```

*Konkretne wartości liczbowe τ są parametrami konfiguracyjnymi KarmazynOS — nie są zapisane w Konstytucji. Konstytucja definiuje tylko relację porządkową.*

---

## Słownik terminów

| Termin | Definicja |
|--------|-----------|
| φ-space | 15-wymiarowa przestrzeń semantyczna; stan systemu |
| attractor | stabilny punkt lub region do którego dąży ewolucja systemu |
| Fixed Point F | stan x taki że `f(x) = x`; system jest stabilny w F |
| Operator R | funkcja rekonstrukcji: `R(P(x)) → x'`; most między Workspace a Bubble |
| τ (tau) | próg stabilności; wartość per-warstwa; `τ_atom < τ_ws < τ_bubble` |
| HRR | Holographic Reduced Representation; mechanizm kodowania wzorców w Hologramie |
| `.soul` JSONL | format projekcji Bubble na dysk; format jest wtórny wobec φ-state |
| φ_budget | budżet energetyczny Workspace; `Σφᵢ ≤ φ_budget` przez cały TTL |
| TTL | Time To Live; obowiązkowy parametr Workspace; brak TTL = błąd architektury |

---

*Konstytucja Systemu φ · KarmazynOS v1.0 · Maciej Mazur · 2026*

*Dokument żywy — ewoluuje razem z systemem. Każda zmiana wymaga aktualizacji testów w Części III.*
