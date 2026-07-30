# KarmazynOS — Szybki Start

**Czas czytania: ~5 minut**  
**Potrzebujesz: Python 3.10+** (opcjonalnie `numpy` dla HRR)

| Składnik | Wersja |
|----------|--------|
| Jądro | `karmazyn_kernel` **1.1.0** |
| Gość Lua | **`karmazyn_lua 0.9.0`** |
| Boot | `karmazyn_boot` v0.5+ |
| Host API | `karmazyn._VERSION` **1.0.0** |

Pełny runtime: **[runtime_pl.md](runtime_pl.md)** · narzędzia: **[tools_lua.md](tools_lua.md)** · macierz: **[lua_bin_status.md](lua_bin_status.md)** · pakiet: **[../LUA/README.md](../LUA/README.md)**

---

## Instalacja

```bash
git clone https://github.com/Maciej-EriAmo/KarmazynOs
cd KarmazynOs
pip install numpy          # opcjonalne
```

**Źródło Lua:** monorepo `LUA/` (kanon).

---

## 1. Start systemu

```bash
python karmazyn_boot.py
```

```text
karmazyn> x = 10
karmazyn> return x * 2
20
karmazyn> :tool ls
karmazyn> :help
```

```bash
python karmazyn_boot.py --demo
python karmazyn_boot.py --project LUA/examples/hello
python karmazyn_boot.py --lisp          # mini-Lisp
```

---

## 2. Projekt wieloplikowy

```bash
python karmazyn_boot.py --project LUA/examples/hello
# :check | :run | require "lib.greeter"

cd LUA
python run_lua.py run examples/hello
```

**Sandbox = bąbel** — host montuje projekt i `karmazyn.*`.

---

## 3. Narzędzia (`lua_bin`)

```text
karmazyn> :tool
karmazyn> :tool whoami
karmazyn> :tool step
karmazyn> :tool kedit
```

**26/28** w smoke; **skip / deprecated w automatyzacji:** `top`, `nano` (tylko ręcznie).

---

## 4. Bramka 0.9

```bash
python software/test_lua_release.py
# RELEASE GATE OK  karmazyn_lua 0.9.0

python software/lua_bin_matrix.py
```

---

## Status

| | |
|--|--|
| **0.9.0** | domyślny gość skryptowy + tools + projekty |
| **1.0** | stabilny kontrakt hosta bez breaking bez major |
| **Nie jest** | pełna Lua 5.5 / ambient Uniks |

Archiwum ksh → `archiwum/`.
