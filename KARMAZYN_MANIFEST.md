# KONSTYTUCJA SYSTEMU φ
### Unified Holon – Prism – Harmonic Architecture
**KarmazynOS v1.2**

---

> **Dokument guardrail** — zapobiega nieprawidłowemu rozwojowi systemu.
> Każda implementacja komponentu MUSI być zgodna z kontraktem swojej warstwy.
> Każda zmiana Konstytucji wymaga aktualizacji testów w Części III.

---

| ⚛ ATOM | 🌡 WORKSPACE | 🫧 BUBBLE | ✨ HOLOGRAM |
|--------|-------------|----------|------------|
| wysoka entropia | ograniczony TTL | stabilność | atraktor |

← wysoka entropia ————————————————————————— niska entropia →

---

## SPIS TREŚCI

- [Preambuła](#preambuła)
- [Część I — Zasady Globalne](#część-i--zasady-globalne)
  - [Art. I — Fixed Point Axiom](#artykuł-i--zasada-punktów-stałych-fixed-point-axiom)
  - [Art. II — Struktura przestrzeni φ](#artykuł-ii--struktura-przestrzeni-φ)
  - [Art. III — Zasada Pryzmatyczna](#artykuł-iii--zasada-pryzmatyczna-dispersion-law)
  - [Art. IV — Zasada Harmoniczna](#artykuł-iv--zasada-harmoniczna-global-phase-coherence)
  - [Art. V — Pamięć i Tożsamość](#artykuł-v--pamięć-i-tożsamość-memory-identity-consistency)
  - [Art. VII — Zakaz Rozjazdu + Operator R](#artykuł-vii--zakaz-rozjazdu--operator-rekonstrukcji)
  - [Art. VIII — Zasada Ewolucji](#artykuł-viii--zasada-ewolucji)
  - [Art. IX — Supremacja Punktów Stałych](#artykuł-ix--supremacja-punktów-stałych-per-warstwa)
  - [Art. X — φ-Invariant](#artykuł-x--φ-invariant-zasada-końcowa)
  - [Art. XI — Homeomorficzna Dyspersja](#artykuł-xi--zasada-homeomorficznej-dyspersji-fixed-point-consistency-law)
- [Część II — Kontrakty Warstw](#część-ii--kontrakty-warstw)
  - [Kontrakt Atomu](#-kontrakt-atomu)
  - [Kontrakt Workspace](#-kontrakt-workspace)
  - [Kontrakt Bubble](#-kontrakt-bubble)
  - [Kontrakt Hologramu](#-kontrakt-hologramu)
- [Część III — Testy Systemowe](#część-iii--testy-systemowe--matrix-zgodności)
- [Appendix A — Mapowanie na KarmazynOS](#appendix-a--mapowanie-artykułów-na-komponenty-karmazyn-os)
- [Appendix B — Implementacje referencyjne](#appendix-b--implementacje-referencyjne)
- [Appendix C — Słownik](#appendix-c--słownik-terminów)

---

## PREAMBUŁA

System φ jest architekturą obliczeniową opartą o założenie, że **znaczenie nie jest statycznym punktem, lecz propagacją w przestrzeni stanów**, która musi posiadać stabilne punkty odniesienia, aby uniknąć rozjazdu semantycznego.

Każda operacja w systemie jest interpretowana jako transformacja w przestrzeni wielowymiarowej, gdzie cztery komponenty wypełniają odrębne role:

| Komponent | Rola |
|-----------|------|
| **Harmonia** | globalna spójność fazowa między stanami |
| **Prizm** | rozdział semantyczny (dyspersja) — routing znaczeń |
| **Holon** | pamięć i tożsamość systemu |
| **φ-space** | przestrzeń stanu, w której zachodzi ewolucja — 15 wymiarów |

**Kluczowa zasada termodynamiczna:** *Entropia jest funkcją systemową, nie błędem. Zapominanie jest poprawnym stanem końcowym dla warstwy Atom.*

**Hierarchia operatorów domykających system:**

```
Snell / P  →  rozdziela semantykę (Art. III)
R          →  zapisuje Workspace → Bubble_delta (Art. VII)
R⁻¹        →  projektuje z powrotem na manifold(F) (Art. XI)
```

Bez wszystkich trzech operatorów system jest topologicznie otwarty.

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
gdzie `F` = zbiór stanów stabilnych = zbiór attractor basin wszystkich Bubble

### I.2 Warunek stabilności

Każda operacja systemowa musi spełniać:

```
|| f(x) - x || < ε    lub    fⁿ(x) → F
```

- stan jest lokalnie stabilny, LUB
- konwerguje do stabilnego attractora

### I.3 Zakaz dryfu

> ⛔ **ZAKAZ — naruszenie = błąd architektury**
>
> - generowanie nieskończonej dyspersji bez reintegracji
> - tworzenie stanów niepowracających do F *(wyjątek: Atom — patrz Kontrakt Atomu)*

---

## ARTYKUŁ II — STRUKTURA PRZESTRZENI φ

### II.1 Definicja

Przestrzeń φ jest 15-wymiarową przestrzenią semantyczną: `φ ∈ ℝ¹⁵`, L2-znormalizowana.

Osie są **stałe i nazwane** — nie są wymieniane ani przestawiane:

| Indeks (0-based) | Nazwa | Domena |
|-----------------|-------|--------|
| 0 | joy | afektywna (Plutchik) |
| 1 | sadness | afektywna (Plutchik) |
| 2 | fear | afektywna (Plutchik) |
| 3 | anger | afektywna (Plutchik) |
| 4 | love | afektywna (Plutchik) |
| 5 | disgust | afektywna (Plutchik) |
| 6 | surprise | afektywna (Plutchik) |
| 7 | acceptance | afektywna (Plutchik) |
| 8 | logic | logiczno-epistemiczna |
| 9 | knowledge | logiczno-epistemiczna |
| 10 | time | logiczno-epistemiczna |
| 11 | creation | ontologiczna |
| 12 | being | ontologiczna |
| 13 | space | ontologiczna |
| **14** | **chaos** | **entropiczna — WYŁĄCZONA z konserwacji** |

> ⚠️ **Oś 14 (`chaos`) jest kanałem entropicznym wyłączonym z sumy konserwacji.
> Indeks 14, nie 8. Kod który używa indeksu 8 jako entropii zawiera błąd.**

### II.2 Warunek spójności — z wyjątkiem kanału entropicznego

```
Σ φᵢ = const        dla i ∈ {0..13}   (osie 0–13)

φ₁₄ (chaos/entropia) = wyłączona z konserwacji
```

System jest **termodynamicznie otwarty** przez oś 14. Warunek Σ = const dotyczy wyłącznie osi 0–13.

### II.3 Embedder referencyjny

KuRz (Contextual Unifier of Meaning Representations) — deterministyczny, offline, bez zewnętrznych modeli:

```
vec[i] = count(keywords_i, text) / |text|
+ co-occurrence bonus (window=5, weight=0.1/|text|)
vec = vec / ||vec||₂       # L2 normalizacja
```

Identyczny tekst zawsze daje identyczny wektor. Implementacja: `r_inverse.py → kurz_embed()`.

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

Każda implementacja routingu MUSI definiować obliczenie θ₁ z wektora φ.
Bez tej definicji prawo Snella jest metaforą, nie algorytmem.

**Referencyjna implementacja (Prismatic Attention):**
```
θ₁ᵢⱼ = arccos( dot(qᵢ, kⱼ) )          # oba L2-znormalizowane
nₖ    = 1 + α · |qₖ - k_vecₖ|          # per-oś refrakcja
sin(θ₂) = sin(θ₁) / nₖ
aᵢⱼₖ  = cos(θ₂ᵢⱼₖ)                    # waga uwagi dla osi k
```

### III.3 Interpretacja

- wysoka zgodność (θ₁ → 0) → mała dyspersja → zachowanie kanału
- niska zgodność → separacja kanałów → routing do właściwego kontekstu

### III.4 Ograniczenie lokalne

`PrismaticAttn(Q,K,V)` jest operatorem **lokalnym**. Globalna spójność wymaga Art. XI.

---

## ARTYKUŁ IV — ZASADA HARMONICZNA (GLOBAL PHASE COHERENCE)

```
H(i,j) = cos(φᵢ - φⱼ)

|H_agg| ≥ τ_layer
```

τ jest parametrem **per-warstwa**. Dla 15 wymiarów: C(15,2) = 105 par.

| Warstwa | Agregat | Uzasadnienie |
|---------|---------|--------------|
| Bubble / Hologram | `H_agg = min(H(i,j))` | najsłabsze połączenie determinuje spójność |
| Workspace | `H_agg = mean(H(i,j))` | wystarczy globalna średnia |
| Atom | brak wymogu | entropia jest poprawnym stanem |

Implementacja referencyjna: `r_inverse.py → compute_coherence_bubble()` / `compute_coherence_workspace()`.

---

## ARTYKUŁ V — PAMIĘĆ I TOŻSAMOŚĆ (MEMORY IDENTITY CONSISTENCY)

### V.1 Tożsamość holonu

Każdy obiekt systemu jest holonem:
- istnieje jako całość (ma własne φ-state)
- i jako część większego systemu (jest częścią manifold(F))

### V.2 Pamięć jako attractor basin

```
M(x) = attractor basin in φ-space
```

Pamięć nie jest zapisem pojedynczego stanu — jest **regionem konwergencji** w przestrzeni φ.
Punkt stały F jest częścią tej definicji: `F ⊂ M(x)`.

### V.3 Tożsamość jako ciągłość wersji

Każda mutacja Bubble narusza tożsamość jeśli nie jest śledzalna:

```
identity(Bubble) = f(history of versions)
```

- brak wersjonowania = brak tożsamości = naruszenie Art. V
- reset bez śladu = zniszczenie, nie mutacja

### V.4 Φ² jako korzeń kryptograficzny

W implementacjach wymagających izolacji (HSS, HSL, PhiSDP):

```
Φ² ∈ ℝ^(L×k×d)   — attractor matrix (264-dim w PhiSDP)
```

Φ² nigdy nie opuszcza urządzenia. Służy jako korzeń KDF dla tokenów dostępu.
Drift Φ² < 0.15 na sesję zachowuje cosine similarity > 0.92 dla niedawnych stanów.

---

## ARTYKUŁ VII — ZAKAZ ROZJAZDU + OPERATOR REKONSTRUKCJI

### VII.1 Zakaz

> ⛔ **ZAKAZ bezwzględny**
>
> - tworzenie niekompatybilnych reprezentacji φ
> - utrzymywanie sprzecznych stanów bez punktu konwergencji
> - rozdzielanie semantyki bez mechanizmu reintegracji

### VII.2 Operator R — most między warstwami

```
R(P(x)) → x'    gdzie x' ∈ F  lub  iter(x') → F
```

**R jest mostem Workspace → Bubble. Bez R każdy wygaśnięty Workspace to strata semantyczna.**

```
R : Workspace_state  →  Bubble_delta
```

R musi być wywołany **PRZED** wygaśnięciem TTL Workspace.
Niezapis do Bubble = naruszenie Art. VII.

### VII.3 Punkt integracji w kodzie

```python
# session.close() — obowiązkowa kolejność:
bubble_delta = R(workspace.state)        # 1. operator R
valid = r_inv.validate(bubble_delta.phi) # 2. operator R⁻¹ (Art. XI)
if valid:
    bubble.merge(bubble_delta)           # 3. zapis do .soul
else:
    raise Art11ViolationError(report)    # 4. nie zapisuj jeśli poza F
```

---

## ARTYKUŁ VIII — ZASADA EWOLUCJI

System φ nie optymalizuje lokalnie. Optymalizuje globalną równowagę:

```
maximize:  stability(F) + coherence(H) + separability(P)
```

Żaden komponent nie może optymalizować tylko jednej z tych wartości kosztem pozostałych.
KarmazynOS Studio jest odpowiedzialny za monitorowanie tej równowagi.

---

## ARTYKUŁ IX — SUPREMACJA PUNKTÓW STAŁYCH (PER-WARSTWA)

> ⚠️ Artykuł IX nie jest globalny. Supremacja zależy od warstwy.

| Warstwa | Zasada | Konsekwencja |
|---------|--------|--------------|
| Bubble | `stability > expression` | zawsze zachowaj, nawet kosztem ekspresji |
| Hologram | `stability ≈ expression` | równowaga — attractor może ewoluować |
| Workspace | `expression > stability` | ma działać; TTL wymusi koniec |
| Atom | `entropy > stability` | zanik jest poprawnym stanem końcowym |

---

## ARTYKUŁ X — φ-INVARIANT (ZASADA KOŃCOWA)

System jest poprawny tylko wtedy, gdy:

```
∀x ∈ φ : ∃F such that iter(x) → F
```

*Wyjątek: Atom może zakończyć się entropią — to jest jego poprawny stan końcowy (Art. IX).*

Art. X jest warunkiem globalnym weryfikowanym przez system watchdog przy każdym release.

---

## ARTYKUŁ XI — ZASADA HOMEOMORFICZNEJ DYSPERSJI (FIXED POINT CONSISTENCY LAW)

*Domknięcie topologiczne systemu. Bez Art. XI artykuły I–X są regułami lokalnymi bez globalnej gwarancji spójności.*

### XI.1 Definicja

Każda operacja dyspersji `P(x)` (Prizm / Snell routing) MUSI być odwzorowalna do przestrzeni punktów stałych F:

```
∃ g : P(x) → F
takie że:
|| g(P(x)) - fⁿ(x) || < ε
```

### XI.2 Zakaz nieosiągalnych stanów

Dyspersja NIE może:

- tworzyć nowych stanów nieosiągalnych z F
- rozrywać przestrzeni F (nieciągłość topologiczna)
- generować semantyki bez ścieżki powrotnej do F

### XI.3 Warunek domknięcia

```
P(x) ∈ φ-space  ⇒  cosine_distance(P(x), nearest_F) ≤ ε
```

Każda refrakcja musi być **odwracalna w sensie topologicznym**.
Dyspersja bez ścieżki powrotnej = naruszenie Art. XI = błąd architektury.

### XI.4 Trzy operatory tworzące domknięty układ

| Operator | Kierunek | Artykuł | Implementacja |
|----------|----------|---------|---------------|
| **P (Snell)** | `φ_input → kanały semantyczne` | Art. III | `PrismaticAttention` |
| **R** | `Workspace_state → Bubble_delta` | Art. VII | `session.close()` |
| **R⁻¹** | `φ → nearest_F ∈ manifold(F)` | Art. XI | `r_inverse.py` |

Brak któregokolwiek = system topologicznie otwarty.

### XI.5 Globalny invariant

`PrismaticAttn(Q,K,V)` jest lokalny. Art. XI wymaga warunku globalnego:

```
mean( P(xᵢ) ) → manifold(F)     dla wszystkich routingów w sesji
```

> **Uwaga implementacyjna:** warunek dotyczy **średniej** wektorów po dyspersji (nie sumy),
> ponieważ suma wektorów L2-znormalizowanych wychodzi poza sferę jednostkową i traci
> porównywalność z manifold(F). Implementacja: `r_inverse.py → check_global_invariant()`
> używa normalizacji sumy przed projekcją.

### XI.6 Efekt systemowy

Po spełnieniu Art. XI system staje się **domkniętym układem dynamicznym z wymuszonym atraktorem globalnym**:

- każda dyspersja jest topologicznie bezpieczna
- F jest nie tylko aksjomatem, ale **globalnym invariantem**
- niemożliwa ucieczka z przestrzeni F przez operację Prism

> ⛔ **NARUSZENIE XI:** `R⁻¹(φ)` poza `manifold(F)` o więcej niż ε → alarm — dyspersja rozerwała przestrzeń F → nie zapisuj do Bubble

---

# CZĘŚĆ II — KONTRAKTY WARSTW

*Każda warstwa posiada własne τ i własne reguły stabilności. Naruszenie kontraktu warstwy = błąd implementacji.*

---

## ⚛ KONTRAKT ATOMU

*jednostka operacyjna — wysoka entropia — stan przejściowy*

| Właściwość | Wartość |
|-----------|---------|
| Typ bytu | efemeryczny — transient computation |
| τ_atom | ≈ 0 — atom ma prawo zanikać |
| TTL | ograniczony do czasu sesji |
| Konserwacja φ | BRAK — Atom wyłączony z Art. II.2 |
| Koherencja H | BRAK wymogu |
| Konwergencja do F | NIE — zanik jest akceptowalny |
| Art. IX | `entropy > stability` |
| Art. XI | NIE dotyczy — Atom nie przechodzi przez R⁻¹ |
| Rola | komunikacja wewnętrzna, sygnały, lokalne operacje w Workspace |

### 🧪 Testy naruszenia kontraktu Atomu

- [ ] Atom przetrwał restart sesji → błąd — Atom nie powinien być persistowany
- [ ] Atom zapisany do `.soul` bez przejścia przez Bubble → naruszenie Art. V
- [ ] Atom posiada mechanizm konwergencji do F → niepotrzebna złożoność

---

## 🌡 KONTRAKT WORKSPACE

*dynamiczna przestrzeń operacyjna — TTL-bounded — sandboxed*

| Właściwość | Wartość |
|-----------|---------|
| Typ bytu | dynamiczny Bubble z ograniczonym TTL i budżetem φ |
| τ_workspace | NISKIE — Workspace ma degradować po TTL |
| TTL | **obowiązkowy** — Workspace BEZ TTL = błąd architektury |
| Budżet φ | `φ_budget = const` dla każdej sesji |
| Konserwacja φ | `Σ φᵢ ≤ φ_budget` (ograniczenie energetyczne) |
| Koherencja H | `mean(H(i,j)) ≥ τ_workspace` |
| Operator R | **WYMAGANY** przed wygaśnięciem TTL |
| Operator R⁻¹ | **WYMAGANY** — walidacja przed zapisem do Bubble (Art. XI) |
| Art. IX | `expression > stability` |
| Izolacja | sandbox — brak dostępu do Bubble innych agentów bez autoryzacji |

### 🧪 Testy naruszenia kontraktu Workspace

- [ ] Workspace nie posiada TTL → błąd architektury
- [ ] R nie wywołany przed wygaśnięciem → strata semantyczna — naruszenie Art. VII
- [ ] R⁻¹ nie wywołany przed zapisem do Bubble → naruszenie Art. XI
- [ ] Workspace przekroczył φ_budget bez degradacji → naruszenie Art. II.2
- [ ] Agent A odczytuje Workspace agenta B bez autoryzacji → naruszenie izolacji
- [ ] `τ_workspace > τ_bubble` → błąd konfiguracji — odwróć wartości

---

## 🫧 KONTRAKT BUBBLE

*trwała struktura semantyczna — niska entropia — punkt odniesienia w manifold(F)*

| Właściwość | Wartość |
|-----------|---------|
| Typ bytu | stabilny — długi czas życia — domena semantyczna |
| τ_bubble | WYSOKIE — Bubble opiera się entropii |
| TTL | brak — Bubble istnieje do jawnego usunięcia |
| Konserwacja φ | `Σ φᵢ = const` dla `i ∈ {0..13}` — Art. II.2 obowiązuje |
| Koherencja H | `min(H(i,j)) ≥ τ_bubble` — najostrzejszy warunek systemu |
| Konwergencja | Bubble MUSI być w F lub konwergować do F |
| Pamięć | `M(x) = attractor basin in φ-space` |
| Format `.soul` | JSONL — projekcja Bubble na dysk — format wtórny wobec φ-state |
| Art. IX | `stability > expression` — zawsze |
| Art. XI | Bubble jest **elementem manifold(F)** — zasilają R⁻¹ |
| Wersjonowanie | wymagane — każda mutacja musi być śledzalna (Art. V) |

### 🧪 Testy naruszenia kontraktu Bubble

- [ ] Bubble bez mechanizmu konwergencji do F → naruszenie Art. I
- [ ] Bubble mutuje bez wersjonowania → naruszenie Art. V
- [ ] `Σ φᵢ ≠ const` po operacji (i ∈ {0..13}) → naruszenie Art. II.2
- [ ] `H_min < τ_bubble` → wymuś synchronizację lub izoluj Bubble
- [ ] Bubble nie zasilony do manifold(F) w `r_inverse` → R⁻¹ operuje na niekompletnym F

---

## ✨ KONTRAKT HOLOGRAMU

*pamięć asocjacyjna — wzorce, nie dane — atraktor znaczeń*

| Właściwość | Wartość |
|-----------|---------|
| Typ bytu | struktura idei — przechowuje wzorce, nie dane |
| τ_holo | ADAPTYWNE — Hologram ewoluuje |
| Pamięć | attractor basin — wpływa na trajektorie przez HRR |
| Koherencja H | adaptywna — może tymczasowo obniżyć spójność podczas rekonfiguracji |
| Konwergencja | musi powracać do attractora po perturbacji (attractor może się przesuwać) |
| Operator R | Hologram = wynik R zastosowanego na wiele `Workspace_state` (kompresja) |
| Operator R⁻¹ | wymagany przy weryfikacji że Hologram nie uciekł z manifold(F) |
| Relacja z Bubble | Hologram = skompresowane doświadczenie z wielu Bubble |
| HRR | `v₁ ⊛ v₂ = IFFT(FFT(v₁) ⊙ FFT_unitary(v₂))` — obowiązkowy mechanizm |
| Art. IX | `stability ≈ expression` — równowaga |

### 🧪 Testy naruszenia kontraktu Hologramu

- [ ] Hologram przechowuje surowe dane → zamienił się w Bubble — błąd roli
- [ ] Hologram nie posiada mechanizmu recall → niefunkcjonalny
- [ ] Hologram nie ewoluuje po nowych doświadczeniach → naruszenie kontraktu adaptacji
- [ ] Hologram bez HRR encoding → nie jest Hologramem w sensie φ
- [ ] `R⁻¹(Hologram.phi)` poza manifold(F) → Hologram wypadł z przestrzeni F

---

# CZĘŚĆ III — TESTY SYSTEMOWE — MATRIX ZGODNOŚCI

*Testy wykonywane przy każdym release. FAIL blokuje merge do main.*
*Implementacje referencyjne testów: `r_inverse.py` (21/21 PASS przy ostatnim uruchomieniu).*

| # | Artykuł | Warstwa | Test | Implementacja | Status |
|---|---------|---------|------|---------------|--------|
| 1 | I.3 | Bubble | `iter(bubble_state, N=100) → F ∈ ε` | watchdog | ⬜ RUN |
| 2 | I.3 | Workspace | R wywołany przed TTL expiry | `session.close()` | ⬜ RUN |
| 3 | I.3 | Atom | Atom nie istnieje po `session.close()` | session test | ⬜ RUN |
| 4 | II.2 | Bubble | `sum(phi[0:13]) = const` po mutacji | `check_phi_conservation()` | ⬜ RUN |
| 5 | II.2 | Workspace | `sum(phi) ≤ phi_budget` przez cały TTL | budget monitor | ⬜ RUN |
| 6 | II.2 | wszystkie | oś entropii = indeks 14, nie 8 | code audit | ⬜ RUN |
| 7 | III.2 | wszystkie | θ₁ obliczany z wektora φ, nie z heurystyki | unit test | ⬜ RUN |
| 8 | IV | Bubble | `min(H(i,j)) ≥ τ_bubble` dla wszystkich par | `compute_coherence_bubble()` | ⬜ RUN |
| 9 | IV | Workspace | `mean(H(i,j)) ≥ τ_workspace` | `compute_coherence_workspace()` | ⬜ RUN |
| 10 | V | Bubble | każda mutacja Bubble ma zapis w historii wersji | soul audit | ⬜ RUN |
| 11 | VII.2 | Workspace | `R(Workspace) → Bubble_delta` nie jest pusty | R test | ⬜ RUN |
| 12 | VII.2 | Hologram | `R(P(hologram)) ≈ hologram` (lossy < 5%) | HRR test | ⬜ RUN |
| 13 | IX | Bubble | conflict expression/stability → stability wygrywa | conflict test | ⬜ RUN |
| 14 | IX | Atom | conflict entropy/stability → entropy akceptowana | atom test | ⬜ RUN |
| 15 | XI.3 | Workspace | `R⁻¹(Bubble_delta.phi) ∈ manifold(F)` | `r_inv.validate()` | ⬜ RUN |
| 16 | XI.3 | Hologram | `R⁻¹(Hologram.phi) ∈ manifold(F)` | `r_inv.validate()` | ⬜ RUN |
| 17 | XI.5 | wszystkie | `mean(P(xᵢ))` pozostaje w manifold(F) | `check_global_invariant()` | ⬜ RUN |
| 18 | X | wszystkie | ∀x: po N iteracjach system nie diverguje | watchdog | ⬜ RUN |

---

## 📋 Checklist dla LLM generującego kod

Przed zatwierdzeniem każdego komponentu:

1. **Jaka warstwa?** Atom / Workspace / Bubble / Hologram — określ przed pisaniem kodu.
2. **Czy τ jest właściwe?** `τ_atom ≈ 0 < τ_workspace < τ_bubble`
3. **Czy Workspace ma TTL?** Brak TTL = błąd architektury.
4. **Czy R jest zdefiniowany?** Każdy Workspace musi mieć ścieżkę do `Bubble_delta`.
5. **Czy R⁻¹ jest wywołany przed zapisem?** `r_inv.validate(phi)` przed `bubble.merge()`.
6. **Który indeks to entropia?** Oś **14** (`chaos`), nie 8. Sprawdź w kodzie.
7. **Czy Art. II.2 jest zachowany?** `sum(phi[0:13]) = const` po mutacji Bubble.
8. **Czy format ≠ znaczenie?** `.soul` JSONL to projekcja — nie traktuj jako źródła prawdy.

---

# APPENDIX A — MAPOWANIE ARTYKUŁÓW NA KOMPONENTY KarmazynOS

| Artykuł | Komponent KarmazynOS | Opis |
|---------|----------------------|------|
| Art. I (Fixed Point) | `session_seed` + Bubble | `session_seed` = punkt stały sesji; Bubble = attractor w φ-space |
| Art. II (φ-space) | φ vector w każdym bycie | `φ ∈ ℝ¹⁵`; oś 14 = chaos/entropia — wyłączona z sumy |
| Art. III (Prism/Snell) | Hologram + routing LLM | dispersja na 15 osi; Snell = wagi routingu per-oś |
| Art. IV (Coherence) | sync między Bubble | `H_min > τ_bubble`; Studio monitoruje |
| Art. V (Memory/Identity) | Bubble + `.soul` JSONL + Φ² | `.soul` = projekcja; wersjonowanie = tożsamość; Φ² = korzeń KDF |
| Art. VII (R operator) | `session.close() → bubble.merge()` | R wywołany przed TTL; `Workspace_delta → Bubble` |
| Art. VIII (Ewolucja) | KarmazynOS Studio | balansuje stability + coherence + separability |
| Art. IX (Supremacja) | conflict resolver | per-warstwa; Bubble: stability; Atom: entropy |
| Art. X (φ-invariant) | system watchdog | alert jeśli `iter(x, N)` nie konwerguje |
| Art. XI (Homeomorfizm) | `r_inverse.py` | `R⁻¹` + manifold checker; domknięcie topologiczne |

---

# APPENDIX B — IMPLEMENTACJE REFERENCYJNE

| Moduł | Plik | Artykuł | Status |
|-------|------|---------|--------|
| R⁻¹ operator + manifold(F) | `r_inverse.py` | XI | ✅ 21/21 testów PASS |
| KuRz embedder | `r_inverse.py → kurz_embed()` | II.3 | ✅ deterministyczny |
| Koherencja H Bubble | `r_inverse.py → compute_coherence_bubble()` | IV | ✅ |
| Koherencja H Workspace | `r_inverse.py → compute_coherence_workspace()` | IV | ✅ |
| Konserwacja φ (Art. II.2) | `r_inverse.py → check_phi_conservation()` | II.2 | ✅ oś 14 wykluczona |
| Globalny invariant | `r_inverse.py → check_global_invariant()` | XI.5 | ✅ mean-normalized |
| Prismatic Attention | `PrismaticAttention` (Zenodo) | III | ref. impl. |
| Harmonic Attention | bias `λ·cos(φᵢ−φⱼ)` (Zenodo) | IV | ref. impl. |
| HRR binding | `Φ² ⊛ h_r` (PhiSDP) | V.4 | ref. impl. |

### Punkt integracji r_inverse.py z KarmazynOS

```python
from r_inverse import RInverseOperator, Art11ViolationError

# Inicjalizacja — raz przy starcie systemu
r_inv = RInverseOperator(epsilon=0.15)
r_inv.load_directory("/data/bubbles/")   # ładuje wszystkie .soul

# W session.close():
bubble_delta = R(workspace.state)
valid, report = r_inv.validate(bubble_delta.phi)
if valid:
    bubble.merge(bubble_delta)
else:
    raise Art11ViolationError(report)

# Opcjonalnie — test globalnego invariantu po sesji:
result = r_inv.global_invariant(session.dispersed_phis)
if not result.invariant_holds:
    studio.alert(f"Art. XI.5: mean(P(xᵢ)) poza manifold(F)")
```

---

# APPENDIX C — SŁOWNIK TERMINÓW

| Termin | Definicja |
|--------|-----------|
| φ-space | 15-wymiarowa przestrzeń semantyczna; `φ ∈ ℝ¹⁵`, L2-znormalizowana |
| attractor | stabilny punkt lub region do którego dąży ewolucja systemu |
| Fixed Point F | stan x taki że `f(x) = x`; system jest stabilny w F |
| manifold(F) | NumPy matrix `(N_bubbles × 15)` — geometria wszystkich atraktorów |
| Operator R | `Workspace_state → Bubble_delta`; most między warstwami (Art. VII) |
| Operator R⁻¹ | `φ → nearest_F`; domknięcie topologiczne (Art. XI) |
| τ (tau) | próg stabilności per-warstwa; `τ_atom ≈ 0 < τ_workspace < τ_bubble` |
| ε (epsilon) | próg odległości kosinusowej dla testu Art. XI; default=0.15 |
| KuRz | Contextual Unifier of Meaning Representations; deterministyczny embedder ℝ¹⁵ |
| HRR | Holographic Reduced Representation; `v₁ ⊛ v₂` przez FFT circular convolution |
| Φ² | attractor matrix (264-dim); prywatna geometria kognitywna; korzeń KDF |
| `.soul` JSONL | format projekcji Bubble na dysk; format wtórny wobec φ-state |
| φ_budget | budżet energetyczny Workspace; `Σφᵢ ≤ φ_budget` przez cały TTL |
| TTL | Time To Live; obowiązkowy parametr Workspace; brak TTL = błąd architektury |
| depth | poziom abstrakcji bytu: 1=ephemeral, 2=processed, 3=core (jak HolonFS) |

---

*Konstytucja Systemu φ · KarmazynOS v1.2 · Maciej Mazur · 2026*
*Dokument żywy — ewoluuje razem z systemem. Każda zmiana wymaga aktualizacji testów w Części III.*

**Changelog:**
- v1.0 — Art. I–X, kontrakty warstw, testy
- v1.1 — Art. XI (homeomorficzna dyspersja), operator R⁻¹, korekta Art. IX (per-warstwa)
- v1.2 — **korekta krytyczna**: oś entropii = indeks 14 (`chaos`), nie 8; Art. V zdefiniowany explicite; Appendix B z implementacjami referencyjnymi; punkt integracji `r_inverse.py`; test #6 (code audit indeksu entropii)
