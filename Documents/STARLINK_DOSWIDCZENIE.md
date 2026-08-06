# Doświadczenie Starlink na atomach KarmazynOs

**Data runu (artefakty):** 2026-08-04  
**Status MVP Starlink:** zamknięty (fazy 0–3 + raport HTML)  
**Repo runtime:** `C:\Users\drwis\KarmazynOs`  
**Repo skarbca / DB:** `C:\Users\drwis\DBase` (cynober-db / DB_karmin)  
**Kanoniczny EN (cel + proof):** `KarmazynOs/Documents/STARLINK_ATOMS.md`  
**Ten plik:** synteza PL — co udowodniono, granice pamięci, jak powtórzyć, postęp DB_karmin.

---

## 1. Czym było doświadczenie

**Nie** budowaliśmy trackera Starlinka ani konkurenta do map satelitarnych.  
**Tak** — test substratu pamięci Karmazyn: jedna fizyka termiczna (T × reach) pod realnym, publicznym obciążeniem (~10,7k satelitów).

| Obawa (zwykły stack) | Tu (jeden Store) |
|----------------------|------------------|
| katalog w SQL | atomy `starlink:sat` |
| heatmapa w osobnej DB / serwisie map | atomy `starlink:cell`, **T = gęstość** |
| grupowanie w tabelach | bąble `starlink` / `sats` / `grid` / `shell:N` |
| skrypty + bus zdarzeń | Lua tool + `state_changed` na Store |
| dashboard w osobnym frontcie | PNG + samowystarczalny HTML |

**Prawo jądra (potwierdzone w praktyce):**

> **temperatura mówi *kiedy*** · **osiągalność mówi *czy***

Ten sam cykl życia co media, fact SE i tool OS — nie „mapa + SQL + message bus + panel”.

### Model danych (hybryda)

```text
Bubble root: starlink
  ├─ sats      → starlink:sat   (NORAD / TLE / lat·lon)
  ├─ grid      → starlink:cell  (T = gęstość / heatmapa)
  └─ shell:N   → grupa inklinacji (np. 43°, 53°, 70°, 97°, 98°)
```

Host: `software/starlink_atoms.py`  
Gość: `lua_bin/starlink.lua`, `lua_bin/starlink_hot.lua`  
Wyjścia: `out/starlink_heat.png`, `out/starlink_report.html` (+ `.json`)

---

## 2. Co zostało udowodnione

### 2.1 Teza multi-task (główny dowód)

Na **jednym** Store jednocześnie żyją:

1. pełny katalog satelitów,
2. ogrzane komórki gęstości (heatmapa),
3. bąble shell po inklinacji,
4. haki zdarzeń / query,

a **Lua** czyta **izolowany widok** (projekcja: meta + cells + shell meta), więc heap języka **nie psuje** katalogu źródłowego.

| Problem przed izolacją | Po Faza 3 (`--lua`, isolate domyślnie) |
|-------------------------|----------------------------------------|
| statystyki hosta puchły ~10×–20× od heapa Lua | `alive` katalogu **stałe** po `:tool starlink` |
| jeden Store = „wszystko miesza się z gościem” | guest Store = `project_starlink_view` |

`--lua-shared` = stary tryb (świadomie niebezpieczny dla metryk).

### 2.2 Skala i metryki (run 2026-08-04)

Źródło: `KarmazynOs/out/starlink_report.json` (pełny katalog, SGP4, `--hot-only`).

| Metryka | Wynik |
|---------|-------|
| Katalog (Celestrak supplemental TLE) | **10 768** satelitów |
| Propagacja SGP4 (pełny katalog) | **~203 ms**, **0** błędów prop |
| Komórki z count > 0 (`--hot-only`) | **2055** (nie pełna siatka 36×72 = 2592) |
| HOT / WARM cells | 1391 / 664 |
| Shells (inklinacja) | 43°: 3626 · 53°: 5062 · 70°: 710 · 97°: 1331 · 98°: 39 |
| Store po ingest | **total/alive = 12 823**, bubbles = 8, TOMB/dead = 0 |
| End-to-end (z siecią / cache TLE) | ~**4,3 s** wall; z ciepłym cache TLE dokumentacja podaje **&lt; 0,5 s** na ingest+bin+heat |
| Peak gęstości (max cell) | count 15 (np. `cell:26:39`) |
| HTML | jeden plik: canvas density, PNG, shell bars, top cells, filtr HOT |

**Jakościowo:** gęstość mapy **jest** ciepłem na atomach — nie osobną warstwą wizualizacji odłączoną od prawa GC.

### 2.3 Fazy zamknięte

| Faza | Co | Status |
|------|----|--------|
| 0 Spike | atomy, bąble, PNG | ✅ |
| 1 SGP4 + live | prop publiczny TLE | ✅ |
| 2 hot-only | atomy tylko dla binów z count &gt; 0 | ✅ |
| 3 Lua isolate + tools | osobny guest Store | ✅ |
| HTML report | `--html` / `--open-html` | ✅ |

### 2.4 Czego to *nie* udowadnia

- Nie jest to produkcyjny system operacyjny satelitów ani real-time tracking ops.
- Nie jest to stress test native Rust slab (run MVP na **Python Store** — string id przyjazne Lua).
- Nie jest to full-grid immortal (świadomie `--hot-only` przy pełnym katalogu).
- Nie jest to KarminQL / gossip / KAFD export konstelacji (opcjonalne „next”).

---

## 3. Granice pamięci KarmazynOs (w świetle tego runu i architektury)

Doświadczenie Starlink **oświetla** granice substratu — nie wszystkie są twarde limity kodu, część to **polityka życia** (T × reach × izolacja).

### 3.1 Warstwy pamięci (model)

| Warstwa | Rola | Granica |
|---------|------|---------|
| **Φ (Phi)** | pamięć robocza — konkurencja o uwagę przez T | bez użycia T spada; poniżej progu evaporacja |
| **Bąble** | pamięć długa / struktura reach | bez reach / vacuum — znikają z powierzchni |
| **Hologramy** | przestrzeń generatywna (PCA / idea) | **MAX_ATOMS** zależne od wymiaru D (SNR) — inna oś niż Store atomów mapy |
| **Store (substrat)** | atomy + T + reach-GC | Python: elastyczny HashMap; Rust native: twardsze limity / id |

**Prawo wspólne:** T = *kiedy* działa i jest widoczne; reach = *czy* w ogóle jest w grafie życia.

### 3.2 Granice ujawnione przy Starlink (~10k atomów)

| Granica | Objaw / decyzja | Wniosek |
|---------|-----------------|---------|
| **Pełna siatka vs hot-only** | full grid 5° = 2592 cell atoms nawet puste; hot-only ≈ 2k tylko z gęstością | puste bin-y nie muszą być nieśmiertelnymi atomami — inaczej Store rośnie „na zapas” |
| **Lua na wspólnym Store** | bez isolate host stats ×10–20 | **granica gościa**: skrypt nie może być tym samym namespace’em co katalog; projekcja / osobny Store jest obowiązkowa przy multi-task |
| **String id vs NativeStore** | Starlink wymusza `KARMAZYN_SUBSTRATE=python` (Lua-friendly string id) | Product/native Store = **u32**; host tools ze string id w testach = backend python (`install_product.md` L1) |
| **~13k alive w Python Store** | desktop Windows, bez OOM, e2e sekundy | skala **10⁴ atomów** jest komfortowa na referencyjnym Store; to nie dowód na freestanding slab (MAX_ATOMS 256 w `karmazyn_slab`) |
| **Brak TOMB w runie** | dead/TOMB = 0 po jednym shocie | to snapshot „gorący”; GC i stygnięcie widać dopiero przy thermal scheduler / idle / vacuum w czasie |
| **TLE / sieć** | cache ~2 MB w `out/`; bez netu → `--offline-demo` | pamięć atomów ≠ cache plików; offline jest osobną ścieżką odtwarzania |
| **Hologram (HRR) vs Store mapy** | MAX_ATOMS w hologramie to bound SNR (np. D=64 → ~5–21 konserwatywnie) | **nie mylić** limitu hologramu z limitem Store satelitów — to inne warstwy |

### 3.3 Limity media / SOUL / DB (sąsiadujące, ważne przy DB_karmin)

Starlink nie pchał blobów, ale ten sam stack ma twarde progi mediów (plan multimedia DBase):

| Parametr | Typowa polityka MVP |
|----------|---------------------|
| SOUL `data_b64` | ≤ **64 KiB**; powyżej `media_ref` |
| Max atom w RAM bez fold | propozycja **8–16 MiB** |
| Chunk KAFS | ≤ **1 MiB** (nie film w jednej ramce RPC) |
| JSON-RPC z base64 | odrzucać duże payloady — binarne idą KAFS |
| Gossip | graf + refs, **nie** pełne filmy w SOUL |

### 3.4 Freestanding / slab (inna planeta niż desktop Starlink)

Z roadmapy Rusta (`rust_roadmap_tech.md`):

- `MAX_ATOMS` / `MAX_BUBBLES` w slab: rzędu **256 / 64** (stack-safe),
- brak nieskończonego HashMap na bump allocatorze,
- vacuum bubble auto — ograniczone względem desktop Store.

**Wniosek architektoniczny:** doświadczenie Starlink udowadnia multi-task na **desktopowym** substracie (Python Store, ~10⁴ atomów). Przeniesienie tej samej konstelacji 1:1 na freestanding slab **nie** jest w zakresie MVP — wymagałoby shardów / fold / hot-only + projekcji, nie „wszystkie 10k w slabie”.

### 3.5 Jednym zdaniem

> KarmazynOs **pamięta jak organizm** (ciepło + reach), nie jak magazyn wierszy: granica nie jest tylko „ile GB RAM”, tylko **co trzymać żywe, co tylko widzieć, co oddać GC** — i **czy gość (Lua) siedzi w tym samym Store**.

---

## 4. Jak powtórzyć doświadczenie

### 4.1 Wymagania

| Wymaganie | Szczegół |
|-----------|----------|
| Kod | `C:\Users\drwis\KarmazynOs` (branch z `software/starlink_atoms.py` + `lua_bin/starlink*.lua`) |
| Python | 3.10+ |
| Pakiety | `pip install sgp4 pillow` (raz) |
| Substrat | `KARMAZYN_SUBSTRATE=python` (skrypt ustawia domyślnie — string id) |
| Sieć | dostęp do Celestrak (supplemental Starlink TLE) **albo** cache / offline-demo |
| OS | sprawdzone: Windows desktop |

### 4.2 Komendy (kanoniczne)

```powershell
cd C:\Users\drwis\KarmazynOs
pip install sgp4 pillow

# Pełny katalog publiczny + SGP4 + hot-only + HTML (główny dowód)
python software/starlink_atoms.py --limit 0 --prop sgp4 --hot-only --html --open-html

# + izolowane Lua (dowód, że katalog nie puchnie)
python software/starlink_atoms.py --limit 0 --prop sgp4 --hot-only --lua --html

# Podzbiór szybszy
python software/starlink_atoms.py --limit 400 --prop sgp4 --lua

# Bez sieci (smoke)
python software/starlink_atoms.py --offline-demo --limit 40 --full-grid --html
```

### 4.3 Kryteria „powtórzyło się”

1. `prop_errors == 0` (przy SGP4).  
2. Przy `--limit 0`: rzędu **~10,7k** satelitów (liczba TLE z Celestrak może lekko rosnąć w czasie).  
3. Przy `--hot-only`: cells ≈ bin-y z count &gt; 0 (nie wymuszać 2592).  
4. Po `--lua` (isolate): **catalog alive po = catalog alive przed**.  
5. Pliki w `out/`: `starlink_heat.png`, opcjonalnie `starlink_report.html` + `.json`.  
6. `out/` jest gitignore — artefakty **regenerować**, nie commitować.

### 4.4 Opcjonalne next (nie wymagane do powtórzenia MVP)

- seed w boot (`:tool starlink` na żywym katalogu),
- Studio / SDL blit, `note_visible`,
- eksport KarminQL / KAFD / gossip mirror,
- smoke test w `software/`.

### 4.5 Gdzie czytać dalej

| Plik | Rola |
|------|------|
| `KarmazynOs/Documents/STARLINK_ATOMS.md` | EN — goal, proof, quick start |
| `KarmazynOs/Documents/PLAN_STARLINK_ATOMS.md` | checklista faz (PL) |
| `KarmazynOs/Documents/STARLINK_X_POST.md` | draft posta |
| `KarmazynOs/out/starlink_report.json` | metryki ostatniego full runu |

---

## 5. Postęp prac przy DB_karmin

**DB_karmin** = wspólna baza (lore, Studio, GameStore, …) na silniku **cynober-db / DBase**, z fasadą `karmazyn_kernel.Store` i substratem **native (Rust)** lub **python**.

```text
Aplikacje (lore, Studio, GameStore, Holon mirror, …)
        │
   KarminQL / światy / KAFD          ← warstwa DB_karmin
        │
   karmazyn_kernel.Store
        │
   NativeStore (Rust GC)  |  PythonStore (referencja)
```

### 5.1 Stan pakietu (repo `DBase`)

| Komponent | Stan (ok. 2026-08) |
|-----------|---------------------|
| Pakiet | **cynober-db** — `pyproject` **8.2.1** (README/historie mogą jeszcze wskazywać 8.0.3/8.2.0 na PyPI) |
| KarminQL | v6.x w `cynober_query_engine.py` |
| Kernel | v1.1.0 + substrat Rust `0.1.0-karmazyn-substrate` |
| Protokół | Cynober-Secure-1.2 (HSS + HSL), **bez** REST/HTTP jako kanonu |
| Światy / shardy | v7.1+ światy, v8.0 shardy COLD, replicate manifest-first |

Przełącznik substratu:

```powershell
$env:KARMAZYN_SUBSTRATE = "native"   # default gdy most zbudowany
$env:KARMAZYN_SUBSTRATE = "python"   # golden / awaryjnie / string id (Starlink)
```

### 5.2 Multimedia — plan F0–F6 (MVP complete)

Źródła: `DBase/docs/PLAN_MULTIMEDIA_WDROZENIE.md`, `NA_JUTRO.md`, fakty Holon.

| Faza | Zakres | Status |
|------|--------|--------|
| **0** | MediaAPI local: attach/get, KAFD, limit SOUL | ✅ |
| **1** | Lore Pack + „Dołącz plik” | ✅ (lore) |
| **2** | pipe / open / CLI `karmazyn_media` | ✅ |
| **3** | KAFS over RPC: caps, MEDIA PUT/GET/STAT, client put/get | ✅ |
| **4** | A_STREAM lokalnie: head + `media_seg`, force_stream / threshold, iter_bytes | ✅ |
| **4b** | KAFS PUT/GET ze stream head (env `KARM_MEDIA_STREAM_THRESHOLD`) | ✅ |
| **5** | lore `podglad_media` + panel Podgląd (Tk/PIL jak Luneta); `karmazyn_media_preview` | ✅ (MVP) |
| **6** | `media_index` w manifeście + `sync_missing_media` / pull KAFS | ✅ (MVP) |

**Zasada transportu (udowodniona kierunkiem implementacji):**

- sterowanie = **RPC / KarminQL**,
- binarne = **KAFS**,
- **nie** film w JSON-RPC / base64 SOUL.

### 5.3 Spike dekodera (po MVP mediów)

| Element | Status |
|---------|--------|
| `IncrementalVideoDecoder` — MP4 klatka-po-klatce gdy hot | ✅ spike |
| Audyt canvas | `docs/AUDIT_MEDIA_CANVAS.md` |
| Plan substratu klatek | `docs/PLAN_DEKODERY_SUBSTRAT.md` (D1–D3) |

**Nadal otwarte / opcjonalne:**

- D1: atomy `media_frame` w Store (dziś klatki w RAM clip, nie w substracie),
- mmap reader KAFD,
- async decode worker,
- load-test **50 MiB** E2E + restart serwera,
- pełne E2E „A na serwerze dodaje portret; B w `--rpc` widzi” jako twardy acceptance F5,
- przyrostowy pull &lt; full world gdy brakuje 1 pliku (doprecyzowanie ops F6).

### 5.4 Holon × Karmin (most SE, nie primary runtime)

W **holonOs** (ten workspace):

| Element | Rola |
|---------|------|
| Primary SE | `holon_memory.json` + Φ / handoff / Mneme |
| `holon_backend_karmin.py` | mirror fact/work → KarminEngine |
| CLI | `karmin-slot` / `karmin-sync` / `karmin-export` / `karmin-import` |
| Env | `HOLON_KARMIN_PATH=C:\Users\drwis\DBase` |
| Świadoma granica MVP | in-process Engine; bez pełnego Φ/AII w Karmin; snapshot JSON ≠ multi-GB KAFD media |

Docs: `docs/KARMIN_BRIDGE.md`.  
**SQLite w planie B3 — odrzucone** na rzecz własnego DB_karmin.

### 5.5 Mapa „co jest gdzie”

| Ścieżka | Rola |
|---------|------|
| `C:\Users\drwis\KarmazynOs` | runtime OS / Starlink atoms / Lua tools |
| `C:\Users\drwis\DBase` | **DB_karmin** = cynober-db, KarminQL, media, światy |
| `C:\Users\drwis\holonOs` | pamięć SE agentów (Holon + Mneme); mirror opcjonalny do Karmin |

---

## 6. Wnioski dla zwykłych ludzi

### O co w ogóle chodziło?

Nie budowaliśmy „kolejnej mapy Starlinka”.  
Sprawdzaliśmy, **czy własna pamięć komputera** (Karmazyn) umie w jednym miejscu:

- trzymać katalog tysięcy obiektów,
- liczyć „gdzie jest gęsto” (mapa ciepła),
- grupować rzeczy (np. po orbitach / klasach),
- i pozwalać skryptom to czytać,

**bez** rozdzielania na: bazę + osobny serwis map + kolejkę zdarzeń + panel.

Wyobraź sobie nie szafę z folderami, tylko **pamięć jak w głowie**: rzeczy używane są „ciepłe”, nieużywane stygną i mogą zniknąć.

### Co się udało pokazać?

1. **Działa w realnej skali** — ok. **10 tys.** publicznych satelitów; propagacja orbit ~**0,2 s** na zwykłym PC.  
2. **Jedna pamięć robi kilka rzeczy naraz** — katalog + mapa gęstości + grupy + skrypty, bez klejenia pięciu systemów taśmą.  
3. **Ciepło = mapa** — gęstość to nie ozdobny wykres obok bazy; to sposób, w jaki system pamięta, co jest ważne *teraz*.  
4. **Skrypt nie może zalać katalogu** — gość dostaje **okno widoku**, nie cały dom.  
5. **Puste półki nie muszą żyć wiecznie** — trzymamy bin-y, w których *coś jest* (hot-only).

### Granice po ludzku

| Co | Znaczy |
|----|--------|
| To nie jest system SpaceX | Demonstracja **fizyki pamięci**, nie produkt trackingowy. |
| Pamięć ≠ nieskończony dysk | Ważne jest **co trzymać żywe**, nie tylko „ile GB”. |
| Desktop ≠ mały chip | ~10 tys. obiektów na PC OK; lekkie jądro ma mniejsze limity. |
| Duże pliki osobno | Media idą tunelem (KAFS), nie wklejone w JSON jak tekst. |

### Jedno zdanie

> **Karmazyn pamięta jak organizm, nie jak Excel:** ważne jest ciepłe i w zasięgu; reszta może ostygnąć. Starlink pokazał, że przy ~10 tys. obiektów i mapie gęstości ta idea na zwykłym PC **już działa**.

### Most do DB_karmin = narzędzie firmowe (bez heroizmu)

Po **połączeniu z DB_karmin** (trwały skarbiec: KarminQL, światy, media, sync zespołu) ten sam model przestaje być tylko „ładnym demem”.

Jeśli dane o **masowych obiektach** są **cyklicznie uzupełniane** (co godzinę / dobę / z API / z pliku — jak TLE ze Starlinka), dostajemy w praktyce:

| Potrzeba firmy | Co już wynika ze stacku |
|----------------|-------------------------|
| Katalog tysięcy / dziesiątek tysięcy jednostek | atomy + bąble, nie osobna „mapa w Excelu” |
| Gdzie jest gorąco / gęsto / awaryjnie | T na komórkach / encjach = heatmapa operacyjna |
| Grupy (region, flota, typ, shell) | bąble / bindings |
| Skrypty, reguły, raporty | Lua / KarminQL / HTML — na **projekcji**, nie na brudzeniu źródła |
| Zespół, media, podgląd | DB_karmin media F0–F6 (attach, KAFS, preview, media_index) |
| Historia / backup | KAFD, replicate, mirror Holon↔Karmin |

**Wniosek produktowy:** dla firmy zarządzającej **masą obiektów** (flota, IoT, zasoby terenowe, stacje, paczki, satelity, pojazdy…) rdzeń „żywej mapy + katalogu + ciepła” **nie wymaga osobnego, drogiego monstrum** — wystarczy **cykliczny feed** + ten sam Store / DB_karmin.

**Specjalny wysiłek zaczyna się dopiero przy UX:**

- dashboard „Enterprise”, role, SLA, mapy wektorowe z GIS, SSO, compliance UI — to **warstwa prezentacji i procesu**, nie warstwa fizyki pamięci;
- bez profesjonalnego frontu nadal jest realne narzędzie: CLI, raport HTML, KarminQL, pipe mediów, sync zespołu;
- z dobrym UX staje się **produktem dla operatorów**; bez UX zostaje **silnikiem**, który i tak unosi skalę.

```text
  [ cykliczny feed danych ]
            │
            ▼
   Karmazyn Store (T × reach, hot-only, isolate)
            │
            ▼
      DB_karmin (trwałość, zespół, media)
            │
     ┌──────┴──────┐
     ▼             ▼
  raport/CLI    opcjonalnie: profesjonalny UX
  (już dziś)    (gdy firma tego chce)
```

**Krótko na LinkedIn / notkę:**  
*Przetestowaliśmy pamięć termiczną na ~10,7k publicznych satelitach. Jedna baza-organizm: katalog, mapa ciepła, grupy, skrypty — bez sklejania SQL + map service + bus. Po spięciu z DB_karmin i cyklicznym uzupełnianiu danych to ten sam wzorzec co zarządzanie dowolną masą obiektów w firmie. Profesjonalny UX to opcja, nie warunek działania silnika.*

---

## 7. Podsumowanie w trzech (plus jeden) punktach

1. **Starlink MVP** pokazał, że **jeden atom Store** unosi realny katalog ~10,7k + heatmapę + bąble + Lua, z SGP4 ~0,2 s i HTML — pod warunkiem **hot-only** i **izolacji gościa**.  
2. **Granica pamięci** KarmazynOs to głównie **polityka życia** (T, reach, projekcje, string vs u32, SOUL/media caps), a nie sama liczba „wierszy”; freestanding slab ma **rzędy mniejsze** limity niż desktop Python Store.  
3. **DB_karmin** (DBase / cynober-db **8.2.x**) ma **media stack F0–F6 MVP** + spike incremental video; dalej: ramki w substracie, mmap, load-test dużych plików, dopięcie E2E zespołowego preview/sync.  
4. **Most produktowy:** cykliczny feed + Store + DB_karmin = realne zarządzanie masą obiektów **bez** budowania od zera; profesjonalny UX jest **nadbudową**, nie fundamentem.

---

## 8. Źródła (wewnętrzne)

- `KarmazynOs/Documents/STARLINK_ATOMS.md` — proof EN  
- `KarmazynOs/out/starlink_report.json` — metryki 2026-08-04  
- `KarmazynOs/Documents/ARCHITECTURE.md` — Φ / bubbles / holograms  
- `KarmazynOs/Documents/install_product.md` — znane limity L1  
- `DBase/docs/DB_KARMIN_NATIVE.md` — native substrate  
- `DBase/docs/PLAN_MULTIMEDIA_WDROZENIE.md` — fazy media  
- `DBase/docs/NA_JUTRO.md` — skrót zrobione  
- `DBase/docs/AUDIT_MEDIA_CANVAS.md` + `PLAN_DEKODERY_SUBSTRAT.md`  
- `holonOs/docs/KARMIN_BRIDGE.md` — most Holon  
- Holon memory facts: `[Karmazyn] Starlink …`, `[Karmin] media …` (boot / Mneme)

---

*Dokument syntezy dla agentów i ludzi. §6 — ton LinkedIn / laicy. Regeneracja Starlink: §4. DB_karmin: §5; po D1/load-test — dopisać. Teza firmowa: cykliczny feed + DB_karmin → narzędzie masowych obiektów; UX opcjonalny.*
