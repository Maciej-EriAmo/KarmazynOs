# Karmazyn Language Reference
## Język skryptowy KarmazynOS — Specyfikacja v1.0

**Maciej Mazur — Warsaw, 2026**
**Powiązany projekt:** KarmazynOS (github.com/Maciej-EriAmo/KarmazynOs)

---

## Filozofia języka

Karmazyn (`.karm`) to język deklaratywno-imperatywny dla KarmazynOS — systemu
pamięci termodynamicznej opartego na atomach, bąblach i hologramach.

Kluczowa zasada: **nie opisujesz danych, opisujesz stany interpretacji.**

Każda instrukcja jest aktem ontologicznym — nie tworzysz rekordu,
tworzysz stan istnienia informacji w przestrzeni Φ.

```
informacja = stabilizacja( H ∘ P ∘ A )
```

Język mapuje tę algebrę na czytelną składnię:
- `atom` → jednostka stanu A
- `hologram` → pole korelacji H
- `prism` → operator projekcji P
- `spawn`, `idea`, `session` → operacje kompozytowe
- `schedule`, `monitor`, `step` → temporalność termodynamiczna

---

## Plik .karm

Plik `.karm` to sekwencja instrukcji (statements) wykonywanych liniowo.
Komentarze zaczynają się od `//`.

```
// To jest komentarz
atom foo {
    S = "treść semantyczna"
    E = "kontekst"
    T = 0.9
}
```

Białe znaki i wcięcia są ignorowane. Cudzysłowy (`"`) obowiązują dla
wartości tekstowych.

---

## Instrukcje

### `atom` — Definicja atomu

Atom to minimalna jednostka stanu informacji `(S, E, T)`.
Tworzy atom w przestrzeni Φ i opcjonalnie rejestruje decay.

```
atom <nazwa> {
    S = "<treść strukturalna>"
    E = "<treść semantyczna>"
    T = <liczba>
    decay = <liczba>
}
```

**Pola:**

| Pole | Typ | Domyślnie | Opis |
|------|-----|-----------|------|
| `S` | string | `""` | Sygnatura strukturalna — deterministyczna, wchodzi do HRR |
| `E` | string | `""` | Projekcja semantyczna — lokalna, sesyjna |
| `T` | liczba | `0.9` | Energia stabilności — `T_vac + ΔT·exp(−λ·age)` |
| `decay` | liczba | `0.01` | Współczynnik λ termodynamicznego zaniku |

Wartość `T = immortal` jest traktowana jak `T = 0.9` z zerowym decayem
(atom nieśmiertelny — analogicznie do flagi `immortal` w BubbleStore).

**Mapowanie runtime:**
- `runtime.write(S + " | " + E)`
- `runtime.mark_bubble_for_decay(label, rate=decay)` jeśli decay ≠ 0.01

**Przykład:**
```
atom phi_identity {
    S = "karmazyn node identity holographic anchor"
    E = "phi-space commitment"
    T = 0.99
    decay = 0.001
}
```

---

### `spawn` — Dynamiczne tworzenie agenta

Tworzy atom z treścią i opcjonalnie konsoliduje go do bąbla.

```
spawn <nazwa> with "<treść>" {
    temp <liczba>
    consolidate
}
```

**Pola opcjonalne:**

| Pole | Typ | Domyślnie | Opis |
|------|-----|-----------|------|
| `temp` | liczba | `0.7` | Temperatura inicjalna (wpływa na recall bias) |
| `consolidate` | flaga | nie | Natychmiastowa konsolidacja do BubbleStore |

**Mapowanie runtime:**
- `runtime.write(treść)`
- `runtime.consolidate(label)` jeśli `consolidate`

**Przykład:**
```
spawn agent_a with "Agent A — primary perception layer" {
    temp 0.85
    consolidate
}
```

---

### `hologram` — Pole korelacji atomów

Tworzy hologram HRR z listy atomów. Hologram nie przechowuje informacji —
**wymusza dopuszczalne formy informacji** w polu interferencji.

```
hologram <nazwa> = <atom1> + <atom2> + ... {
    strength: "<wartość>"
    prism: "<CORE|IN|OUT|ALL>"
    temp: <liczba>
    description: "<opis>"
}
```

**Pola opcjonalne:**

| Pole | Typ | Domyślnie | Opis |
|------|-----|-----------|------|
| `strength` | string | `"medium"` | Siła pola (`low`, `medium`, `high`) |
| `prism` | string | `"CORE"` | Przestrzeń projekcji hologramu |
| `temp` | liczba | `0.4` | Temperatura generacji (niższa = stabilniejsza) |
| `description` | string | brak | Metadane opisowe |

Składowe muszą być wcześniej zdefiniowane (`atom` lub `spawn`).
Jeśli bąbel składowej nie istnieje, jest automatycznie tworzony przez `consolidate`.

**Mapowanie runtime:**
- `runtime.consolidate(label)` dla każdej składowej
- `runtime.archive_bubbles_to_hologram(topic, bubble_labels)`

**Przykład:**
```
hologram cognitive_core = phi_identity + memory_kernel + crypto_signal {
    strength: "high"
    prism: "CORE"
    temp: 0.3
    description: "interference field — cognitive core"
}
```

---

### `idea` — Generatywna synteza

Generuje nowy wektor semantyczny z hologramu przez projekcję.
Idea to nie rekord — to **wyłonienie się stanu z pola**.

```
idea "<prompt>" from <hologram_expr> {
    gen "<prompt generacji>"
    temp <liczba>
    consolidate
}
```

**Pola:**

| Pole | Typ | Domyślnie | Opis |
|------|-----|-----------|------|
| `gen` | string | prompt | Zapytanie do `generate_from_idea()` |
| `temp` | liczba | `0.5` | Temperatura generacji (wyższa = więcej szumu) |
| `consolidate` | flaga | nie | Zapisz wynik do BubbleStore |

`hologram_expr` może być nazwą hologramu lub listą atomów (`a + b + c`).
Jeśli podano atomy bezpośrednio, hologram jest tworzony tymczasowo.

**Mapowanie runtime:**
- `runtime.generate_from_idea(hid, prompt, temperature)`
- `runtime.phi.add_semantic_vector(vec, label)`
- `runtime.consolidate(label)` jeśli `consolidate`

**Przykład:**
```
idea "emergent cognitive synthesis" from cognitive_core {
    gen "generate semantic vector from thermodynamic core state"
    temp 0.35
    consolidate
}
```

---

### `prism` — Operator projekcji

Definiuje prism — przestrzeń interpretacji atomów dla agentów.
Agent bez dostępu do prisma nie otrzymuje odmowy — otrzymuje **szum**
(Warp Oblivion: dane nie istnieją w jego świecie).

```
prism <nazwa> {
    mask = <CORE|IN|OUT|ALL>
    visibility = <CORE|IN|OUT|ALL>
    privileges = <CORE|IN|OUT|ALL>
}
```

**Wartości pól:**

| Wartość | Prisms | Opis |
|---------|--------|------|
| `ALL` | `[core, in, out]` | Pełny dostęp |
| `CORE` | `[core]` | Tylko rdzeń semantyczny |
| `IN` | `[in]` | Tylko wejście |
| `OUT` | `[out]` | Tylko wyjście / interfejs zewnętrzny |

**Mapowanie runtime:**
- `runtime.derive_agent(name, task, prisms)`

**Przykład:**
```
prism secure_view {
    mask = CORE
    visibility = OUT
    privileges = IN
}
```

---

### `session` — Sesja agenta

Łączy agenta z prismem i opcjonalnie wykonuje operacje odczytu.

```
session <nazwa> {
    prism: "<wartość>"
    visibility: "<wartość>"
    run <atom_lub_spawn>
    run <inny_atom> with { klucz: "wartość" }
}
```

**Pola:**

| Pole | Typ | Opis |
|------|-----|------|
| `prism` | string | Przestrzeń projekcji sesji |
| `visibility` | string | Widoczność sesji |
| `run` | name | Atom/agent do odczytu przez `read_as_agent()` |

`run` może pojawić się wielokrotnie.

**Mapowanie runtime:**
- `runtime.derive_agent(name, task, prisms)`
- `runtime.read_as_agent(label, pid, s_agent)` dla każdego `run`

**Przykład:**
```
session session_hot {
    prism: "CORE"
    visibility: "ALL"
    run agent_hot
    run phi_identity
}
```

---

### `monitor` — Nadzór liveliness

Rejestruje monitor termodynamiczny dla bąbla. Monitory są sprawdzane
przez `check_monitors()` lub przez `KARM MONITOR` w shellu.

```
monitor liveliness of <nazwa_bąbla> {
    alert_below: <liczba>
    action: "<akcja>"
}
```

**Akcje:**

| Akcja | Opis |
|-------|------|
| `log` | Tylko wydruk alertu (domyślna) |
| `refresh` | `runtime.refresh_bubble(target)` — zeruje decay |
| `revoke` | `runtime.revoke_bubble(target)` → Warp Oblivion |
| `step` | `runtime.step(1)` — krok termodynamiczny |

**Przykład:**
```
monitor liveliness of agent_hot {
    alert_below: 0.5
    action: "refresh"
}
```

---

### `schedule` — Harmonogram cykliczny

Rejestruje reguły wykonywane cyklicznie w wątkach daemon.

```
schedule {
    every <liczba> <jednostka> {
        <instrukcja1>
        <instrukcja2>
        ...
    }
    every <liczba> <jednostka> {
        ...
    }
}
```

**Jednostki czasu:**

| Symbol | Znaczenie |
|--------|-----------|
| `s` | sekundy |
| `m` | minuty (× 60) |
| `h` | godziny (× 3600) |

Każda reguła uruchamia się w osobnym wątku daemon.
Wewnątrz `every` można używać dowolnych instrukcji (w tym `recall`, `step`).

**Przykład:**
```
schedule {
    every 30 s {
        step 1
        recall memory_kernel
    }
    every 1 h {
        step 3
        recall phi_identity
    }
}
```

---

### `step` — Krok termodynamiczny

Wywołuje `runtime.step(n)` — przesuwa czas wewnętrzny systemu.
Każdy krok zmniejsza T atomów przez `T_vac + ΔT·exp(−λ·age)`.

```
step <liczba>
```

**Przykład:**
```
step 3
```

---

### `recall` — Przeszukiwanie pamięci

Przeszukuje przestrzeń Φ i BubbleStore zapytaniem semantycznym.

```
recall <nazwa>
recall <nazwa> every <liczba> <jednostka>
```

Forma z `every` rejestruje cykliczne przeszukiwanie (analogicznie do `schedule`).

**Mapowanie runtime:** `runtime.recall(name, k=5)`

**Przykład:**
```
recall memory_kernel
recall phi_identity every 5 m
```

---

### `import` — Import modułu

Ładuje moduł Python do środowiska executora.

```
import <moduł>
import <moduł>.<podmoduł>
```

**Przykład:**
```
import karmazyn.bridge
import numpy
```

---

## Wartości

| Typ | Przykład | Opis |
|-----|---------|------|
| String | `"tekst"` | Cudzysłowy podwójne, brak escape sequences |
| Number | `0.9`, `42` | Liczba zmiennoprzecinkowa lub całkowita |
| Name | `phi_identity` | Identyfikator (litery, cyfry, `_`) |
| `immortal` | `T = immortal` | Specjalna wartość — wysoka stabilność |
| `ALL` | `mask = ALL` | Wszystkie prismy |
| `CORE` | `prism = CORE` | Tylko rdzeń |
| `IN` | `visibility = IN` | Tylko wejście |
| `OUT` | `mask = OUT` | Tylko wyjście |

---

## Integracja z shellem

### Patch do istniejącego shell.py

```python
from shell_karm_patch import apply_karm_patch

# W shell.py, po definicji RUNTIME, COMMANDS, COMMAND_LIST:
karm = apply_karm_patch(RUNTIME, COMMANDS, COMMAND_LIST)
```

Po dodaniu patcha dostępne są nowe komendy:

```
KARM <plik.karm>        — wykonaj plik
KARM RUN <kod>          — wykonaj inline
KARM LOAD <plik.karm>   — załaduj bez wykonania
KARM EXEC <nazwa>       — wykonaj załadowany
KARM LIST               — lista załadowanych
KARM STATUS             — stan executora
KARM MONITOR [sek]      — monitoring bąbli w tle
KARM STOP               — zatrzymaj scheduler/monitor
```

Komenda `EDIT <plik.karm>` automatycznie wykonuje plik po wyjściu z edytora.

### Standalone shell

```bash
python shell_karm_patch.py                    # REPL
python shell_karm_patch.py thermo_agent.karm  # wykonaj plik
python shell_karm_patch.py --runtime ./data   # z zapisanym stanem
```

---

## Użycie z Python API

```python
from karmazyn import KarmazynOS
from karmazyn_lang import KarmazynExecutor, parse_file, parse_source

# Inicjalizacja
runtime = KarmazynOS()
executor = KarmazynExecutor(runtime)

# Wykonaj plik
executor.run_file("thermo_agent.karm")

# Wykonaj kod inline
executor.run_source("""
    atom test {
        S = "hello karmazyn"
        E = "test atom"
        T = 0.8
    }
    step 1
    recall test
""")

# Dostęp do stanu
print(executor._labels)      # name → runtime label
print(executor._holograms)   # name → hologram_id
print(executor._agents)      # name → (pid, s_agent)

# Monitoring
executor.check_monitors()

# Zatrzymaj scheduler
executor.stop_scheduler()
```

---

## Architektura implementacji

```
karmazyn_lang.py
├── GRAMMAR              — gramatyka Lark LALR + contextual lexer
├── AST nodes            — @dataclass dla każdej instrukcji
├── KarmazynTransformer  — lark.Transformer → AST
├── KarmazynExecutor     — AST → runtime calls
└── ScheduleRunner       — wątki daemon dla schedule

shell_karm_patch.py
├── KarmShellIntegration — dispatcher komend KARM
├── apply_karm_patch()   — patch do shell.py
└── standalone_shell()   — REPL bez shell.py
```

**Zależności:**
- Python 3.10+
- `lark` — parser LALR (`pip install lark --break-system-packages`)
- `karmazyn.py` — runtime KarmazynOS v1.3+
- `numpy` — wektory semantyczne

**Uwaga o lexerze:** Gramatyka używa `lexer='contextual'` (LALR z kontekstowym
lekserem). Terminale kluczowe (`ATOM_KEY`, `HOLO_KEY` etc.) mają priorytet `.2`
aby wygrywać z `NAME` przy single-letter keywords (`S`, `E`, `T`).

---

## Przykładowy program

Patrz: `thermo_agent.karm` — pełny scenariusz trzyagentowy demonstrujący
wszystkie instrukcje języka.

```bash
# Uruchomienie demo
python shell_karm_patch.py thermo_agent.karm

# Lub w shellu
KARM thermo_agent.karm
```

---

## Cykl życia atomu w języku

```
atom foo { S = "..." }       →  CREATED → HOT (Φ-space)
spawn bar with "..." {
    consolidate              →  HOT → bubble (BubbleStore)
}
hologram h = foo + bar {}   →  bubble → hologram HRR
monitor liveliness of bar {
    action: "revoke"         →  liveliness < threshold → Warp Oblivion
}
step 100                     →  T decay → WARM → COLD → TOMB → GC
```

---

## Status

```
Parsowanie LALR         ✅  contextual lexer, priorytety terminali
AST wszystkie nodes     ✅  10 typów instrukcji
Transformer             ✅  self-test 11/11 statements
Executor → runtime      ✅  pełne mapowanie karmazyn.py v1.3
Shell integration       ✅  patch + standalone REPL
Demo program            ✅  thermo_agent.karm
```

---

*"Nie opisujesz danych. Opisujesz stany interpretacji danych w czasie."*

**Autor:** Maciej Mazur
**GitHub:** Maciej-EriAmo/KarmazynOs
**Zenodo:** 10.5281/zenodo.19371554
