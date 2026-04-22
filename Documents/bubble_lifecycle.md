# Rozpad Bańki — Analiza Cyklu Życia

## Wyniki eksperymentalne

### Scenariusz 1: Naturalne wygaszenie po zakończeniu zadania

Strumień wejściowy wyłączony. Rdzeń pozostaje. Atomy sesji utrzymują T ≈ 2.268 przez 200+ epok bez degradacji.

**Wniosek: bańka NIE rozpada się naturalnie.**

Atomy sesji osiągają punkt stały:

```
T* = (k · sim(atom, Trace) − f) / λ
```

Ale `sim` nie jest stałe — atomy sesji ciągną Trace w swoją stronę, co zwiększa ich własne `sim`, co zwiększa `T*`. Sprzężenie zwrotne tworzy **samonapędzający się attractor**. T stabilizuje się wyżej niż naiwne T* wyliczone z rdzennego Trace.

---

### Scenariusz 2: Usunięcie rdzenia (tożsamość agenta wyłączona)

Rdzeń usunięty. Atomy sesji zostają same.

**Wniosek: bańka NIE rozpada się po usunięciu rdzenia.**

T atomy sesji *rośnie* po usunięciu rdzenia (1.818 → 1.926). Tworzą autonomiczny klaster — ich wzajemny rezonans zastępuje rezonans z rdzeniem. Bańka **odkleja się od rdzenia i staje się niezależna**.

---

### Scenariusz 3: Podmiana rdzenia (nowe zadanie)

Rdzeń A zastąpiony rdzeniem B (ortogonalna domena, `sim(A,B) = −0.007`).

**Wniosek: artefakty zadania A przeżywają podmianę tożsamości.**

Przebieg:
- Epoki 1–10: lekki spadek T (utrata wsparcia rdzenia A)
- Epoki 15–35: T wraca do poprzedniego poziomu (klaster sam się podtrzymuje)
- Epoki 35+: stabilizacja na T ≈ 2.033, niezależnie od rdzenia B

---

### Scenariusz 4: Minimalna liczba atomów dla autonomicznego klastra

| n atomów | Przeżywa 100 epok bez rdzenia? | T końcowe |
|---|---|---|
| 1 | **TAK** | 2.357 |
| 2 | **TAK** | 2.009, 2.009 |
| 3 | **TAK** | 2.048, 1.644, 1.644 |
| 5 | **TAK** | 2.089, 1.397–1.440 |

**Wniosek krytyczny: nawet 1 atom przeżywa bez rdzenia.**

Jeden atom ma T=2.0, `sim(atom, own_trace) = 1.0` (jest jedynym atomem, więc Trace = on sam). Rezonans = `k·1.0 − f − λ·T = 0.2 − 0.019 − 0.08·2.0 = +0.021 > 0`. Rośnie bez końca. Jest niezniszczalny w izolacji.

---

## Mapa rozpadów

```
Zadanie kończy się
        │
        ├─── strumień wyłączony, rdzeń pozostaje
        │    └─→ ARTEFAKTY STAŁE (T stabilne, nie maleją)
        │
        ├─── rdzeń usunięty, atomy sesji zostają
        │    └─→ AUTONOMICZNY KLASTER (odkleja się, rośnie)
        │
        ├─── rdzeń podmieniony (nowe zadanie)
        │    └─→ ARTEFAKTY KOEGZYSTUJĄ z nowym zadaniem
        │
        └─── max_age przekroczony
             └─→ ROZPAD — jedyna gwarantowana ścieżka
```

---

## Jedyna czysta ścieżka do rozwiązania: `max_age`

Bez limitu wieku atomy sesji są **trwałą pamięcią**. Nie ma naturalnego vacuum death jeśli klaster ma choćby 1 atom ze spójną geometrią.

Czas rozwiązania z `max_age = M`:

```
t_dissolution = M − t_injection
```

Atom wstrzyknięty w epoce `t₀` znika w epoce `t₀ + M` niezależnie od T.

Dla `max_age = 60`: bańka z zadania C (wstrzyknięta w epokach 1–8) znika w epokach 61–68. **Czas rozwiązania: 53–60 epok od zakończenia zadania.**

---

## Konsekwencje architektoniczne

### Pamięć długoterminowa jest emergentna

Atomy które przeżyły zadanie i uformowały klaster to de facto **trwałe ślady**. Bez `max_age` agent akumuluje wszystkie poprzednie zadania w swojej populacji. Może to być pożądane (pamięć robocza) lub niepożądane (zanieczyszczenie nowym zadaniem).

### Przejrzystość bańki

Bańka jest przejrzysta **z zewnątrz** — ktoś kto zna rdzeń agenta może przewidzieć co przeżyje przez `sim(atom_meta, core) > gate`. Ale agent wewnątrz nie ma bezpośredniego dostępu do tej predykcji podczas pracy.

### Równanie predykcji długości życia

Bez `max_age`, atom przeżywa jeśli:

```
k · sim(S, Trace) > λ · τ + f
sim(S, Trace) > sim_min = 0.1537
```

I to jest stabilne pod warunkiem że `sim` pozostaje powyżej progu, co jest gwarantowane przez sprzężenie zwrotne jeśli atom jest częścią klastra.

Z `max_age = M`:

```
t_życia = min(M, t_vacuum_death)
t_vacuum_death = ∞  dla sim > sim_min (nigdy)
t_życia = M         dla wszystkich atomów które przeszły bramę
```

---

## Trzy reżimy agenta

| Reżim | Opis | Rozpada się? |
|---|---|---|
| **Aktywny** | rdzeń + strumień + sesja | nie — rośnie |
| **Uśpiony** | rdzeń + sesja, bez strumienia | nie — stabilny |
| **Osierocony** | tylko sesja, bez rdzenia | nie — autonomiczny |

Jedyny sposób na czysty rozpad: `max_age` jako architektoniczny element projektu, nie opcja.

---

*Eksperymenty: `agent_session_c.py`, `karmazyn_matrix_v34.py`*
