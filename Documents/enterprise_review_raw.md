# Surowa recenzja enterprise — KarmazynOs

**Data:** 2026-07-31  
**Zakres:** monorepo runtime (kernel, native Rust, software boot/I/O/Studio, docs planów)  
**Perspektywa:** Product / platform engineering / SRE / security / release  
**Ton:** surowy — bez marketingu

---

## 0. Werdykt w 30 sekund

| Pytanie | Odpowiedź |
|---------|-----------|
| Czy to ciekawa architektura? | **Tak** — spójna ontologia T×reach, Rust jako core |
| Czy to Product enterprise-ready? | **Nie** |
| Czy to solidny R&D / Lab z kierunkiem Product? | **Tak, z zastrzeżeniami** |
| Gotowość do „wdrożenia u klienta / w firmie” | **~25–35%** (host-only lab) |
| Go / No-Go na external pilot | **No-Go** bez L1 release + CI + ownership artefaktów |
| Go / No-Go na kontynuację wewnętrzną | **Go** — z twardym Z0 i domknięciem uncommitted |

**Jedno zdanie:**  
Masz **mocny rdzeń ideowy i częściowo zrealizowany native Store**, ale **brak enterprise control plane** (CI, jeden gate, release hygiene, security baseline, czysta granica modułów) — i **sesja Feature’ów leży niezacommitowana**.

---

## 1. Executive scorecard (1–5)

| Obszar | Ocena | Komentarz |
|--------|------:|-----------|
| Architektura domenowa (Φ, T, reach) | **4** | Spójna, udokumentowana, nietrywialna |
| Architektura implementacji (warstwy) | **3.5** | Z0 + mapa Rust dobre; szwy Python wciąż grube |
| Jakość substratu Rust | **3.5** | `cargo test` OK; mały crate; std-only; brak no_std path |
| Jakość hosta (boot/I/O/Studio) | **3** | Stage 1 sensowny; Studio MVP; dużo `except Exception` |
| Testy / quality gates | **2.5** | Lokalne unittesty; **brak CI**; boundary **exit 1** |
| Release / versioning | **2** | VERSION.txt jest; brak CHANGELOG, tag nie obejmuje nowej fali |
| Operacje / observability | **1.5** | BootLog OK; brak metrics, tracing, SLI |
| Security | **1.5** | Brak threat model na Studio/host; SDL surface; nie SBOM |
| Dokumentacja strategiczna | **4** | Plany mocne (build, GRUB, Rust map, Z0) |
| Dokumentacja operatorska | **2** | Brak `install_product.md`, `gate_product` |
| Governance / single source of truth | **2** | Lustra root vs software; untracked docs; dual paths |
| **Średnia ważona (Product)** | **~2.4** | Lab wyżej (~3.2), enterprise niżej |

---

## 2. Co jest naprawdę dobre (nie odbierać)

1. **Decyzja Rust na substracie** — właściwa warstwa, uzasadniona (ownership, GC graph).  
2. **Z0 „Rust pisze od razu pod substrat”** — enterprise-grade principle; rzadkość w projektach research.  
3. **Prawo jądra jednozdaniowe** — da się auditować i testować.  
4. **Dual-track native/python** — golden + Product; dojrzały odruch.  
5. **Stage 1 I/O** — name→aid, twarde FAIL, anti self-heat; to jest *platform thinking*.  
6. **Mapa dokumentów** — `rust_substrate_map`, `build_deploy_plan`, `io_stage1`, `grub_loader_plan` — powyżej średniej open-source research.  
7. **Separacja Studio (SDL) od jądra** — zgodne z Lunetą i z Z0.  
8. **Istniejące release Lua 1.1.x** — dowód, że potrafisz domykać gościa.

To nie jest chaos hobby „wszystko w jednym pliku”. To jest **platforma w stadium foundation**.

---

## 3. Krytyczne ustalenia (P0) — blokery enterprise

### P0-1 — Stan repozytorium ≠ stan narracji

`git status`: **dużo zmodyfikowanych + cała fala `??` untracked** (I/O, Studio, plany, lustra root).

| Ryzyko | Skutek |
|--------|--------|
| Brak commit/tag | niereprodukowalny release |
| Docs tylko lokalnie | „plan istnieje” tylko na jednej maszynie |
| Lustra `karmazyn_*.py` w root | dryf import path |

**Enterprise:** nie ma *deployment*, dopóki nie ma *immutable revision*.  
**Akcja:** jeden commit (lub stack) „runtime: stage1 io + studio + plans”; tag po G0.

### P0-2 — `kernel_boundary` FAIL (exit 1)

```
XX karmazyn_kernel -> karmazyn_backend  (TWARDE: jadro importuje oprogramowanie)
WYNIK: NARUSZENIE (1)
```

Plus doradcze: `karmazyn_io → karmazyn_atom`, `backend → substrate`.

**Interpretacja surowa:**

- Albo **narzędzie jest nieaktualne** (`karmazyn_backend` nie jest w zbiorze KERNEL, mimo że leży w `kernel/`).  
- Albo **granica jest realnie rozmyta** i narracja „twarda granica” jest **fałszywa reklamą**.

Oba warianty są złe dla enterprise:  
**gate w planie G0 jest czerwony** — a plan mówi, że ma być zielony.

**Akcja:** albo dopisz `karmazyn_backend` do KERNEL allowlist (jeśli to kanon), albo przenieś backend poza fasadę; **io nie importuje `karmazyn_atom` wprost** — tylko `karmazyn_kernel` / stałe z jednego miejsca. Gate musi być zielony w CI.

### P0-3 — Brak CI / jednego `gate_product`

Plan wymaga `scripts/gate_product.ps1` — **pliku nie ma**.  
**Brak `.github/workflows`.**

Bez CI:

- Z0 nie jest egzekwowane (review ad hoc),  
- native wheel/DLL nie jest budowany na PR,  
- regresja boundary/testów jest *opcjonalna*.

**Enterprise minimum:** PR pipeline: `cargo test` + `unittest` subset + `kernel_boundary` exit 0.

### P0-4 — Brak operatorskiego „day-1 install”

Brak `Documents/install_product.md`.  
Nowy inżynier / klient: **nie ma runbooka** (rustup, MSVC vs MinGW, maturin, pygame, PYTHONPATH).

Plan L1 „≤ 30 min od zera” jest **niesprawdzalny** bez tego dokumentu i bez świeżego dry-run.

---

## 4. Poważne (P1)

### P1-1 — Dwa światy id: string vs u32

Rust: `u32`. Python reference / lua_bin tools: często **string ids**.  
Host tools **wymusza python** w testach — Product native + tools ze string id = **mina**.

**Enterprise:** Product path musi mieć **jeden kontrakt id** na powierzchni host API (albo tools tylko po name_to_aid / int).  
Inaczej „default native” jest marketingiem, a realne tooli żyją na reference.

### P1-2 — `NativeStore.create_atom(string_id)` zwraca int i gubi semantykę id

To jest **cicha utrata kontraktu** (requested id w metadata, realny id int).  
Dla enterprise: API powinno **failować głośno** na nieobsługiwanym id albo mapować 1:1 w warstwie adaptera z dokumentacją.

### P1-3 — Ogrom `except Exception` w boot/io/studio

Typowy smell: połykanie błędów → trudny on-call.  
Stage 1 thermal mount FAIL jest OK; reszta bootu nadal **zbyt tolerancyjna** (Lua mount paths, host install, etc.).

**Enterprise:** klasyfikacja błędów: *fatal / degraded / ignore* + metryka.

### P1-4 — Studio = pygame, nie kontrakt display

OK na Lab. Na „enterprise workstation product”:

- zależność natywna,  
- brak headless policy poza `--check`,  
- brak wersjonowania UI,  
- input nie jest audytowalny (brak logu security).

### P1-5 — Plany > egzekucja

Masz lepszą **dokumentację drogi** niż **automatyzację drogi**.  
W enterprise to klasyczny failure mode: *architecture theater* — o ile nie domkniesz A/D (gate + tag).

### P1-6 — Dual mirror root/software

Import zależny od `PYTHONPATH` / cwd.  
**Single source of truth** nie jest wymuszony technicznie.

---

## 5. Średnie (P2)

| ID | Temat | Uwaga |
|----|--------|------|
| P2-1 | Brak CHANGELOG | Release hygiene |
| P2-2 | Brak SBOM / pin wersji wheel | supply chain |
| P2-3 | Brak metryk (tick rate, reaped, T_console) | SRE |
| P2-4 | HRR opcjonalne numpy — float nondeterminism | science vs product |
| P2-5 | Lua host 1.x vs native int — niespójność narzędzi | product UX |
| P2-6 | GRUB/ISO tylko na papierze | OK jeśli L1 first; nie sprzedawać jako bootable OS |
| P2-7 | Bezpieczeństwo Studio (local code exec via shell) | threat model zero |
| P2-8 | Brak license/compliance scan deps | cargo/pip |

---

## 6. Architektura — ocena enterprise

### Mocne

- Czysty **core domain** w Rust.  
- Seams (C ABI, PyO3) — textbook hexagonal-ish.  
- Gość nie w core.  
- I/O jako matryca T — spójne z ontologią (nie „osobny event bus UI”).

### Słabe / enterprise gaps

| Wzorzec enterprise | Stan |
|--------------------|------|
| API versioning / deprecation policy | częściowo (host 1.x, ABI string) — brak procesu |
| Compatibility matrix (OS × Python × rustc) | brak tabeli testowanej |
| Feature flags formalne | env ad hoc |
| Multi-tenant / isolation | N/A (local OS) — OK, ale nazwij scope |
| Disaster recovery | brak (poza python rescue w planie) |
| Audit log | brak |
| Secrets management | N/A dziś; HSL/HSS w przyszłości — puste |

**Ocena architektoniczna:** *foundation of a product platform*, nie *enterprise product*.

---

## 7. Bezpieczeństwo (surowo)

| Powierzchnia | Ryzyko | Uwaga |
|--------------|--------|--------|
| Shell / Lua tools | RCE w kontekście usera | zamierzone lab; nie „secure runtime” |
| Studio SDL | input → eval_line | brak sandbox policy poza bąblem |
| Native DLL | load path hijack | Windows DLL search order niezaudytowany |
| PyO3 wheel | supply chain | brak pin hash w release |
| Boundary FAIL | false sense of isolation | gate czerwony |

**Nie twierdź** publicznie o „bezpiecznym OS” na bazie HSS paper, dopóki host path nie ma threat model + boundary zielony.

---

## 8. Operacje / SRE

| Praktyka | Stan |
|----------|------|
| Health check | boot sequence log — ad hoc |
| Metrics | brak |
| Structured logging | brak (print/BootLog) |
| Alerting | N/A |
| Runbooks | fragmentaryczne docs |
| On-call ownership | single-dev implied |
| Capacity / perf budget | bench_substrate istnieje — nie w gate |

**BootLog** jest dobrym zarodkiem *startup probe* — nie ma *liveness* ani *readiness* API.

---

## 9. Testy — prawda vs plan

| Gate w planie | Rzeczywistość (2026-07-31) |
|---------------|----------------------------|
| cargo test | ✅ ok |
| unittest io/host/studio | ✅ lokalnie |
| kernel_boundary | ❌ exit 1 |
| gate_product script | ❌ nie istnieje |
| CI | ❌ nie istnieje |
| test_lua_release | nie odpalony w tej recenzji (założenie: był zielony historycznie) |
| compat native↔python | zależny od zbudowanego wheel |

**Wniosek:** jakość Lab jest OK; **quality system** enterprise nie istnieje.

---

## 10. Z0 — recenzja zasady

Z0 jest **właściwa i enterprise-correct**.

Ryzyko: Z0 jest na razie **w markdown**, nie w **process**:

- brak CODEOWNERS na `native/karmazyn_substrate/`  
- brak CI „fail if store law changed only in python”  
- łatwo złamać pod presją „szybki fix w PythonStore”

**Rekomendacja:** pre-commit / CI diff rule: zmiany w `karmazyn_substrate.py` (prawo) wymagają równoległej zmiany w `native/.../src` lub label `reference-only`.

---

## 11. Product positioning (brutalnie)

| Można sprzedawać / obiecywać dziś | Nie można |
|-----------------------------------|-----------|
| Research runtime / memory OS lab | „Gotowy system operacyjny” |
| Native Store GC engine (library) | Bootowalny Karmazyn ISO |
| Studio do eksploracji matrycy T | Enterprise support / SLA |
| Lua guest tools na host | Portable product bez Python |

**Nadużycie narracji = największe ryzyko reputacyjne** przy Twoim stacku (HSS, papers, OS language).

---

## 12. Macierz Go / No-Go

| Cel | Werdykt | Warunek |
|-----|---------|---------|
| Kontynuacja R&D | **GO** | commit fali + Z0 w review |
| Wewnętrzny daily driver (REPL/Studio) | **GO z limitem** | native build udokumentowany |
| Release L1 „Product host” | **NO-GO dziś** | G0 zielony w CI + tag + install doc |
| Pilot zewnętrzny | **NO-GO** | L1 + threat model + support path |
| ISO / GRUB demo | **NO-GO** | po L1; inaczej teatr |
| Twierdzenie „samodzielny OS” | **NO-GO** | dopiero L4 |

---

## 13. Top 10 działań (kolejność ROI enterprise)

1. **Commit + PR** całej fali (io, studio, plans) — immutable baseline.  
2. **Napraw `kernel_boundary`** do exit 0 (allowlist lub refaktor importów).  
3. **`scripts/gate_product.(ps1|sh)`** = jedna komenda G0.  
4. **CI** na PR (cargo + unittest + boundary).  
5. **`install_product.md`** + dry-run na czystej VM.  
6. **io: import T constants via kernel facade**, nie `karmazyn_atom` wprost.  
7. **Host tools / create_atom** — kontrakt id na native (fail loud lub map).  
8. **Tag L1** dopiero po 1–7.  
9. Dopiero potem BootConfig / ISO.  
10. CODEOWNERS + branch protection na `native/karmazyn_substrate`.

---

## 14. Podsumowanie ocenowe

| Persona | Werdykt |
|---------|---------|
| **CTO research lab** | Kontynuować; to ma zęby. |
| **VP Engineering product** | Za wcześnie na roadmapę zewnętrzną; domknij foundation. |
| **SRE** | Brak platformy operacyjnej — nie bierz on-call. |
| **Security** | Lab only; nie wystawiać powierzchni bez modelu. |
| **Investor pitch „OS company”** | Overclaim risk wysoki — trzymaj język „runtime / substrate”. |

---

## 15. Final cut

KarmazynOs w obecnym kształcie to:

> **Wysokiej jakości zalążek platformy pamięciowo-termicznej z natywnym jądrem w Rust, owinięty w dojrzałe plany i niedojrzały delivery system.**

Słabość nie leży w wizji ani w wyborze `rustc`.  
Słabość leży w **egzekucji enterprise**: artefakty niezacommitowane, gate granicy czerwony, brak CI, brak install path, niespójność id, narracja łatwo wyprzedza nośnik.

**Z0 jest właściwy.**  
**L1 nie jest zamknięty.**  
**L2–L4 to spekulacja, dopóki L1 nie jest nudny i powtarzalny.**

---

*Recenzja surowa — do użytku decyzyjnego, nie marketingowego.*
