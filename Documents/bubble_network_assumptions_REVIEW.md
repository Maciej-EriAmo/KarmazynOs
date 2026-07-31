# Recenzja: `bubble_network_assumptions.md` (v0.4)

**Dokument recenzowany:** `Documents/bubble_network_assumptions.md`  
**Data recenzji:** 2026-07-25  
**Recenzja dotyczy wersji założeń:** 0.4  

**Werdykt:** dokument **mocny jako theory-of-ops i kotwica granicy** — lepiej niż typowy „vision doc”.  
Nie jest jeszcze **specyfikacją protokołu** ani **security proof**. Jako v0.x założeń: **akceptowalny z poprawkami** (kilka sprzeczności pojęciowych i jedna poważna dwuznaczność „HSS”).

---

## 1. Ocena ogólna

| Kryterium | Nota | Komentarz |
|-----------|------|-----------|
| Jasność tezy centralnej | **9/10** | Bąbel = nośnik; Wi‑Fi = L0 — domknięte od §1 |
| Dyscyplina „co to nie jest” | **9/10** | §1.2, §5.6, §13.4 — rzadko spotykana uczciwość |
| Spójność z jądrem (T / reach) | **8/10** | A4 i merge by T trzymają linię Karmazyn |
| Rozdział hipotezy vs implementacji | **8/10** | §13 vs §15 dobrze; „HSS” psuje czystość |
| Użyteczność dla implementatora | **6/10** | §8 + §15 pomagają; brak stanów, błędów, normatywności |
| Bezpieczeństwo (threat model) | **7/10** | §6.3, §14, §15.5 solidne intuicyjnie; bez adversary formalnego |
| Ryzyko overclaim | **niskie–średnie** | Kontrolowane; żywy klucz i „rewolucja Wi‑Fi” są oznaczone |

**Jednym zdaniem recenzenta:**  
to dobry dokument **filozofii i mapowania**, z jedną dziurą pojęciową (dwa HSS) i z niedomknięciem, czy Surface to *bąbel* czy *phi-space atomów*.

---

## 2. Mocne strony

1. **Naprawiona metafora (§1.3)** — od razu tnie half-truth „zamiast Wi‑Fi”.  
2. **Aksjomaty A1–A7** — krótkie, testowalne w dyskusji; A3 i A5 to rdzeń wyróżnika.  
3. **Warstwy L0–L4** — czytelny podział ontologia / hydraulika.  
4. **§14 (zakłócenia)** — najlepsza merytorycznie część: sitko ontologiczne + nowe wektory + założenia projektowe (heat tylko od uprawnionego rezonansu).  
5. **§15 (DBase)** — rzadki luksus: teoria spięta z kodem, z **rejestrem luk** zamiast marketingu „już mamy wszystko”.  
6. **§15.8 reguła spójności dokumentów** — praktyczna dyscyplina utrzymania.  
7. **Kryteria sukcesu §12** — da się z nich zrobić checklistę eksperymentów.

---

## 3. Problemy krytyczne / wysokie

### K1. Dwa znaczenia „HSS” (najpoważniejsze)

Dokument używa **HSS** jako:

| Znaczenie A | Znaczenie B |
|-------------|-------------|
| przestrzeń agentów: Trace, Core, gate, `emission_sim` (§5–§6, HSS v0 paper) | KEM Ring-LWE w `karmazyn_hss.py` / handshake (§7, §15) |

§15.7 to przyznaje, ale **za późno i za cicho**. W §3 L2 = „HSS — pole widoczności…”, a w §15.4 L2 = „HSS KEM + reguły widoczności” — to **sklejenie dwóch warstw w jedną nazwę**.

**Skutek:** czytelnik z DBase myśli „mamy HSS”, czytelnik z paperu agentowego myśli o gate — i obie strony mają rację o czym innym.

**Rekomendacja:** w v0.5 wprowadzić rozróżnienie nazewnicze, np.:

- **HSS-KEM** / **HSS-crypto** — uścisk, kraty  
- **HSS-field** / **H-space** / **visibility plane** — Trace, gate, emisja  

Albo L2 rozbić na **L2a widoczność geometryczna**, **L2b KEM sesji** (KEM może siedzieć bliżej L3 z HSL).

---

### K2. Surface = bąbel, ale implementacja = phi-space atomów

§4: Surface **jest bąblem** (wiązania, korzeń, revoke bąbla).  
§15: KSH sync to głównie **atomy w RAM**, SOUL/bąble osobno.

To nie jest kłamstwo (lukę zapisano), ale **centralna metafora dokumentu nie jest zrealizowana w mapowaniu 1:1**. Tytuł „sieć bąblowa” obiecuje bąbel; wire daje snapshot Φ-atomów.

**Rekomendacja:**

- albo osłabić A1 na v0.x: *„nośnik jest powierzchnią w substracie (bąbel lub równoważny korzeń Φ)”*,  
- albo podnieść lukę §15.7 do **P0 ewolucji** z jawnym kryterium: *„Surface = bąbel z bindings, nie tylko lista atomów”*.

---

### K3. Normatywność: założenie vs wymóg vs hipoteza

Dokument miesza tryby:

| Tryb | Przykłady |
|------|-----------|
| aksjomat (musi) | A1–A7 |
| kontrakt logiczny | §8 Emit/Sense |
| hipoteza | §13, żywy klucz §15.6 |
| opis stanu kodu | §15.1–15.5 |
| „poza zakresem” | §11 — nadal oznaczone „v0.1” przy dokumencie 0.4 |

Brak legendy: **MUSI / POWINIEN / MOŻE / HIPOTEZA / STAN**.

**Rekomendacja:** krótka tabela RFC-like na początku + tagi przy §13 i §15.6.

---

## 4. Problemy średnie

### M1. HSL vs HSS w L2/L3 — granica rozmyta

§6: HSS = kto widzi.  
§7: HSL = czy wolno interpretować.  
W DBase „brak rezonansu HSL” też odcina sens — blisko gate HSS.

Dla czytelnika: *czy zła sesja HSL to L2 czy L3?*  
W praktyce Cynober oba kończą się „szumem”.

**Rekomendacja:** jedno zdanie: *odrzucenie kryptograficzne sesji = L3; cisza geometryczna bez klucza = L2; UX może być identyczny (brak faktu w Φ).*

### M2. „Routing binarny względem gate” (§6.2)

W paperze HSS bywa binarny empirycznie; w systemie z szumem wektorowym i tolerancją KEM to uproszczenie.

**Rekomendacja:** „binarny w modelu idealnym; implementacja może mieć pasmo niepewności / hysteresis gate”.

### M3. Merge multi-master

§4.3 i §11: konflikt termiczny + wersja sesji, ale multi-master **poza zakresem**, podczas gdy KSH już robi merge by T A↔B.  
Czytelnik nie wie: *czy merge by T jest kanonem, czy tylko KSH?*

**Rekomendacja:** przenieść „merge by higher T (+ tiebreak node_id)” do **założeń kanonicznych A↔B**, a multi-master (>2, partycje) zostawić poza zakresem.

### M4. Lua w §10.6 vs §15.7

§10: Lua domyślny język Surface.  
§15: Lua nie jest stroną wire.  
Prawda, ale wygląda na sprzeczność „domyślny” vs „niepodpięty”.

**Rekomendacja:** *„Lua = domyślny L4 w KarmazynOS boot; Cynober L4 = KarminQL; wspólny kontrakt Surface, różne fronty.”*

### M5. Ścieżki absolutne Windows w §15.1

`C:\Users\drwis\DBase` — kruche w repo / dla innych maszyn.

**Rekomendacja:** `DBase/` lub `…/DBase` + „sibling monorepo”.

### M6. §11 „poza zakresem (v0.1)”

Kosmetyka wersji; myli z v0.4.

### M7. Brak diagramu sekwencji OpenSession

§8 i §15.2 są tabelaryczne; jedna sekwencja (A/B, Faza 0–4, potem Emit/Sense) mocno by pomogła.

### M8. Żywy klucz termiczny — za mało constraintów w dokumencie

§15.6 ma wzór i ducha; brak:

- stabilizacja okna (min/max rekey),  
- co jeśli T jest publicznie obserwowalne,  
- czy `H_thermal` to secret material czy binder,  
- odporność na adversary znający model decay.

Rozmowa projektowa to doprecyzowała; **dokument założeń jeszcze nie**.

---

## 5. Problemy lekkie / redakcja

- Trzy „jednozdaniowe podsumowania” (§13.6, §14.7, §15.9, §16) — OK, ale warto spis treści z etykietami *rdzeń / zakłócenia / branża / implementacja*.  
- Powtórzenia Wi‑Fi disclaimer (~4×) — świadome, można skrócić odsyłaczem do §1.2.  
- Brak spisu treści na górze (dokument ~640 linii).  
- Brak definicji skrótów na starcie (Φ, PrismMask, TOMB, SOUL).  
- „§ rozmowa” w §15.5 — niearchivowalne; lepiej „ustalenia projektowe 2026-07”.  
- Literówka stylu: „garantowanego” → „gwarantowanego” (§5.6).

---

## 6. Luki merytoryczne (czego brakuje, jeśli to ma być „założenia sieci”)

| Luka | Priorytet |
|------|-----------|
| Model tożsamości węzła (Φ² vs Core vs node_id) — jedna tabela | wysoki |
| Stany Surface: `nascent / live / cooling / revoked / forked` | wysoki |
| Semantyka błędów Sense (cisza vs deny vs noise) — czy w ogóle rozróżnialne dla gościa | średni |
| Budżet: jednostki, domyślne limity, co przy przekroczeniu | średni |
| Zegar / epoka / skew (KSH ma 300 s replay — brak w ontologii) | średni |
| Privacy / fingerprinting z `H_thermal` i Φ² | średni |
| Relacja do loader → kernel → comm (§9) vs realny boot Lua | niski |
| Testy akceptacyjne §12 → konkretne scenariusze w DBase/tests | wysoki na później |

---

## 7. Spójność wewnętrzna (checklist)

| Para | Status |
|------|--------|
| §1 „nie Wi‑Fi PHY” ↔ §13 | OK |
| A4 T/reach ↔ §14.3 D termika | OK |
| A5 no ambient ↔ §15.5 | OK |
| A1 bąbel ↔ §15 KSH atomy | **napięcie** (udokumentowane, ale centralne) |
| §3 L2 HSS-field ↔ §15 L2 HSS-KEM | **napięcie** |
| §8 Emit/Sense ↔ §15.3 KarminQL | OK jako przybliżenie |
| §11 merge poza zakresem ↔ KSH merge by T | **drobna niespójność** |
| Żywy klucz „nie na zawsze” ↔ brak w KDF | OK (hipoteza) |

---

## 8. Czy dokument spełnia swój status?

Status recenzowanego pliku: *„dokument granicy / theory-of-ops”*.

| Obietnica statusu | Spełnia? |
|-------------------|----------|
| Granice (co jest / nie jest siecią) | **tak** |
| Theory-of-ops (jak myśleć o warstwach i atakach) | **tak** |
| Mapowanie na istniejącą implementację | **tak** (§15) |
| Spec wire / formal security | **nie** (i nie obiecuje) |
| Gotowość do kodowania Surface API w KarmazynOS | **częściowo** — brak stanów i norm MUST |

**Wniosek:** status jest trafny; nie udawać, że to RFC.

---

## 9. Rekomendowana kolejność poprawek (v0.5 założeń)

1. **Nazewnictwo HSS** (K1) — rozdziel KEM vs pole widoczności.  
2. **Doprecyzuj Surface** (K2) — bąbel vs phi-space; P0 w lukach.  
3. **Legenda MUST/HIPOTEZA/STAN** (K3).  
4. **Merge by T** jako kanon A↔B; multi-master poza zakresem.  
5. **Żywy klucz** — 5–7 bulletów constraintów (sekret + binder, okno, nie publiczny termometr).  
6. Spis treści + słowniczek skrótów.  
7. Ścieżki względne DBase.

Opcjonalnie później: sekwencja OpenSession, stany Surface, mapa testów z §12.

---

## 10. Ocena końcowa

| | |
|--|--|
| **Jakość jako dokument założeń** | **B+ / 8/10** |
| **Gotowość do „rewolucji branżowej”** | świadomie niska (§13.5) — dobrze |
| **Gotowość do ewolucji KSH/HSL** | dobra dzięki §15 |
| **Główne ryzyko** | przeczytanie dokumentu tak, jakby Trace-gate HSS i Ring-LWE HSS to to samo „już w production” |

**Rekomendacja recenzenta:**  
**trzymaj jako living assumptions**; nie rozrzucać w kod KarmazynOS nowej sieci od zera; ewolucja przez DBase uścisk + domknięcie ontologii Surface=bąbel.  
Przed kolejną dużą warstwą teorii — **v0.5 tylko na K1–K3** (nazwy, Surface, normatywność). To podniesie dokument z „bardzo dobrego eseju systemowego” do „założeń, z których da się bezpiecznie projektować”.

---

## Historia tej recenzji

| Wersja | Data | Uwagi |
|--------|------|--------|
| 1.0 | 2026-07-25 | Pierwsza recenzja dokumentu założeń v0.4 |
|
