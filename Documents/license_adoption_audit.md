# Audyt licencji i adopcji kodu — KarmazynOs

**Data:** 2026-07-31  
**Cel:** co wolno adoptować, ile kodu jest „nasze”, jakie ryzyka compliance.

---

## 1. Licencja produktu (źródło własne)

| Lokalizacja | Licencja | Copyright |
|-------------|----------|-----------|
| **`LICENSE` (root)** | **MIT** | 2026 Maciej Mazur |
| `native/*/Cargo.toml` | MIT | ten sam autor |
| `Documents/LICENSE` | (sprawdź lokalnie — zwykle kopia / notatka) | |
| **`archiwum/LICENSE`** | **MIT** (ujednolicone 2026-07-31) | wcześniej historyczny tekst GPL |

**README (kanon):**

- Kod w repo: **MIT** (od **2026-07-07**).
- Wcześniej: **GPL-3.0**; forki sprzed tej daty mogą zostać na GPL (decyzja maintainerów forków).
- Publikacje akademickie / Zenodo: **osobne licencje** (nie mylić z kodem).
- Powiązane: [DBase / Cynober](https://github.com/Maciej-EriAmo/DBase) — **MIT**.

### Wniosek adopcyjny (własny kod MIT)

Przy **MIT** możesz (i inni mogą):

- używać komercyjnie, zamykać w produktach, forować, sublicencjonować,
- **warunek:** zachować notice copyright + MIT w kopiach / substantial portions.

**Adopcja własnego kodu do innego Twojego projektu MIT** (np. DBase, nowy monorepo):  
**~100% dozwolone** przy zachowaniu notice.  
**Adopcja do projektu GPL-3** (np. holonOs jeśli GPL): też dozwolone (MIT → GPL jest kompatybilne *w jedną stronę*: MIT kod może wejść do GPL; **nie** odwrotnie bez relicencji).

---

## 2. Archiwum — ujednolicone do MIT (2026-07-31)

`archiwum/LICENSE` jest **MIT** (wcześniej leżał historyczny tekst GPL-3.0 mimo root MIT).

Monorepo (w tym archiwum) = **MIT**, copyright Maciej Mazur.  
Forki zewnętrzne sprzed relicencji root (2026-07-07) mogą nadal być GPL u ich maintainerów.

---

## 3. Zależności zewnętrzne (runtime / build)

### 3.1 Rust (substrat Product)

| Crate | Licencja | Adopcja / użycie |
|-------|----------|------------------|
| **`karmazyn_substrate`** | MIT, **0 deps zewnętrznych** (tylko `std`) | 100% Twój kod |
| **`karmazyn_substrate_rs`** | MIT | Twój kod |
| **`pyo3` 0.25** | **MIT OR Apache-2.0** (dual) | Biblioteka — linkowanie OK; źródła PyO3: zachować notice przy dystrybucji binarek zgodnie z wybraną licencją |

**Wniosek:** rdzeń Product (**Store w Rust**) jest **najczystszy compliance-owo**: MIT + opcjonalnie PyO3 (permissive).

### 3.2 Python host

| Pakiet | Licencja (typowa) | Uwagi adopcji |
|--------|-------------------|---------------|
| **CPython** | PSF | runtime, nie wpinamy źródeł |
| **numpy** | BSD-3-Clause (+ części 0BSD/MIT/Zlib/CC0) | permissive; notice w dystrybucji |
| **maturin** | MIT OR Apache-2.0 | tool build, nie runtime Product |
| **pygame-ce** | **LGPL-2.1** | **Studio only** |

#### pygame-ce / SDL (Studio) — ważne

- **LGPL-2.1:** dynamiczne linkowanie (pip wheel) jest zwykle OK przy dystrybucji aplikacji, z możliwością podmiany biblioteki.
- **Nie wklejaj** źródeł pygame do monorepo na MIT bez spełnienia LGPL (lub bez trzymania jako osobny komponent).
- **Product cold-boot / L4 bez GUI** → **zero pygame** → zero problemu LGPL.
- Studio = **opcjonalny** surface; nie mieszaj z crate substratu (już rozdzielone).

### 3.3 Linux HSS (`holo/*.c`)

Kod własny / most LSM — licencja monorepo MIT (root).  
Uwaga: linkowanie z **jądrem Linux (GPL)** to **osobna** kwestia (kernel modules / GPL linking).  
**Nie traktuj** `holo/` jako „dowolnie zamknięty blob w kernelu” bez porady pod GPL kernel.

### 3.4 Lua

| Warstwa | Licencja / pochodzenie |
|---------|------------------------|
| **`LUA/` karmazyn_lua** | Kod **własny** (interpreter podzbioru na substracie) — MIT monorepo |
| **PUC-Rio Lua** (referencja / testy) | MIT (PUC-Rio) — **nie jest** vendored jako pełny runtime w Product |
| Plan `puc_subset` | Oficjalne testy Lua (MIT) — wolno kopiować **z atrybucją** (już w planie gap) |

**Nie mylić:** `karmazyn_lua` ≠ pełna implementacja PUC; adopcja „kodu Lua z netu” bez licencji = zakaz.

---

## 4. Ile kodu „możemy adoptować” — mapa ilościowa

Przybliżone linie (`.py`/`.rs`, bez `target/`, bez cache), lokalnie:

| Obszar | Pliki | ~LOC | Licencja adopcji | Ile „wolno wziąć” do innego MIT projektu |
|--------|------:|-----:|------------------|------------------------------------------|
| **Rust substrate core** (`native/karmazyn_substrate/src`) | 4 | **~1.1k** | MIT, 0 deps | **100%** (Z0 — preferuj ten kod) |
| **Native bridge Py** (`native/*.py` + bindings) | ~9 | **~3k** | MIT | **~100%** (szew hosta) |
| **kernel/** | 7 | **~2.1k** | MIT | **~100%** (fasada + ref Python Store) |
| **software/** (boot, I/O, Studio, host) | 13 | **~4.8k** | MIT (+ runtime LGPL jeśli bundlujesz pygame) | **~95%** kodu własnego; bez vendoring pygame |
| **LUA/** | 28 | **~8.8k** | MIT (własny gość) | **~100%** własnego; bez roszczenia „to jest Lua.org” |
| **archiwum/** | 70 | **~41k** | **GPL text w LICENSE** — **ostrożnie** | **Nie adoptować hurtowo** bez weryfikacji; preferuj przepisywanie z kanonu 2026 |
| **Documents/** (plany, audyty) | — | — | zwykle copyright autora; papers osobno | wolny reuse wewnętrzny; papers ≠ kod |

### Podsumowanie „ile %”

| Pytanie | Odpowiedź |
|---------|-----------|
| Ile **Product path** (Rust+kernel+software+LUA bez archiwum) jest Twoje pod MIT? | **~20k LOC, praktycznie 100% własności/licencji monorepo** |
| Ile z **archiwum** wolno „wkleić” do MIT Product bez review? | **0% bez weryfikacji** (stary monolit + GPL notice) |
| Ile **zewnętrznego** kodu musisz adoptować do Store? | **0 LOC** w crate (tylko std + opcjonalnie PyO3 jako lib) |
| Ile wolno wziąć z **Holon** (jeśli GPL-3)? | Do Karmazyn MIT: **nie** wklejać kodu GPL do tree MIT bez relicencji Holon→MIT lub izolacji GPL |
| Ile z **Karmazyn → Holon GPL**? | MIT kod **można** wnieść do GPL (z notice); wynik całości często GPL |

---

## 5. Scenariusze adopcji

### A. Nowy projekt / produkt komercyjny na bazie Karmazyn (closed + MIT notice)

| Bierz | Nie bierz na siłę |
|-------|-------------------|
| `native/karmazyn_substrate` | `archiwum/` hurtowo |
| `kernel/` (fasada + backend) | źródła pygame |
| `software/karmazyn_io`, boot | Holon GPL bez relicencji |
| `LUA/` (własny gość) | papers Zenodo jako „kod” |

**Obowiązek:** plik LICENSE / NOTICE z copyright Maciej Mazur + MIT.

### B. Integracja z DBase / Cynober (MIT)

**Kompatybilne.** Można dzielić Store / KarminQL warstwami.  
Z0: wspólne prawo GC → **jeden crate Rust**, nie kopia w Pythonie.

### C. Integracja z Holon (GPL-3 w workspace)

| Kierunek | |
|----------|--|
| Holon → Karmazyn MIT tree | **Blokada** bez zmiany licencji Holon lub dual-license |
| Karmazyn MIT → Holon | **OK** (MIT pozwala; Holon może stać się „GPL + MIT parts”) |
| Tylko API / protokół / pomysły | nie wymaga kopiowania kodu |

### D. Studio z pygame w dystrybucji binarnej

- Dystrybucja **z** pygame wheel: przestrzegaj **LGPL-2.1** (dynamic link, info o bibliotece).  
- Dystrybucja **bez** Studio: brak LGPL w runtime.

### E. Adopcja testów / kodu z Lua.org

- Testy PUC: **MIT** — wolno z atrybucją.  
- Nie twierdź, że `karmazyn_lua` = oficjalne Lua.

---

## 6. Checklist compliance (enterprise)

- [x] Root LICENSE = MIT, autor jasny  
- [x] Cargo.toml license = MIT  
- [ ] Ujednolicić lub opisać `archiwum/LICENSE` (GPL legacy)  
- [ ] `NOTICE` lub `THIRD_PARTY.md` (numpy, PyO3, pygame-ce) przy release binarnym  
- [ ] CI: `cargo deny` / `pip-licenses` (opcjonalnie faza A)  
- [ ] Holon / Karmazyn: **nie mieszać** tree bez policy  
- [x] Substrat Rust bez copyleft deps  

---

## 7. Rekomendacja praktyczna „ile adoptujemy teraz”

| Priorytet | Co adoptować jako kanon Product | ~LOC | Dlaczego |
|-----------|----------------------------------|------|----------|
| **P0** | `native/karmazyn_substrate` (Rust) | ~1.1k | Z0, MIT pure |
| **P0** | `kernel/` + `karmazyn_substrate_native` | ~5k | fasada + most |
| **P1** | `software/` boot + io (+ studio opcjonalnie) | ~5k | host L1 |
| **P1** | `LUA/` | ~9k | gość Product |
| **P2** | Wybrane wzorce z `archiwum/` **przepisane**, nie skopiowane | 0–N | unik GPL ambiguity |
| **Unikaj** | Holon źródła w tree Karmazyn | — | GPL vs MIT |
| **Unikaj** | Vendor pygame | — | LGPL |

**Szacunek „rdzeń możliwy do pełnej adopcji pod MIT bez tarcia”: ~15–20k LOC**  
(Rust + kernel + software + LUA, bez archiwum).

**Szacunek archiwum „potencjalnie cenny, ale nie do ślepej adopcji”: ~41k LOC** — tylko po audycie plik-po-pliku / rewrite.

---

## 8. Jednozdaniowe podsumowanie

> **Karmazyn Product (Rust substrate + kernel + software + LUA) stoi na MIT i prawie w całości da się adoptować; archiwum i Holon wymagają ostrożności (GPL); Studio ciągnie LGPL tylko przez pygame; crate substratu nie ma copyleft dependencies.**

---

*To nie jest porada prawna — przy komercyjnej dystrybucji binariów z pygame/numpy/PyO3 warto krótki przegląd counsel / `THIRD_PARTY.md`.*
