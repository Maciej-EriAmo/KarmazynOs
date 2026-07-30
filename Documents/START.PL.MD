# KarmazynOS — Szybki Start

**Czas czytania: ~5 minut** · Python 3.10+ (opcjonalnie `numpy`)

| Składnik | Wersja |
|----------|--------|
| Jądro | **1.1.0** |
| Gość Lua | **`karmazyn_lua 1.0.0`** (stable) |
| Host API | **`karmazyn._VERSION` 1.0.0** |
| Boot | v0.5+ |

[runtime_pl.md](runtime_pl.md) · [tools_lua.md](tools_lua.md) · [lua_bin_status.md](lua_bin_status.md) · [LUA/README.md](../LUA/README.md)

---

## Instalacja

```bash
git clone https://github.com/Maciej-EriAmo/KarmazynOs
cd KarmazynOs
pip install numpy   # opcjonalne
```

Kanon Lua: monorepo **`LUA/`**.

---

## Start

```bash
python karmazyn_boot.py
python karmazyn_boot.py --demo
python karmazyn_boot.py --project LUA/examples/hello
```

```text
karmazyn> x = 10
karmazyn> return x * 2
karmazyn> :tool ls
karmazyn> return karmazyn._VERSION
```

CLI bez pełnego OS:

```bash
cd LUA
python run_lua.py run examples/hello
```

**Sandbox = bąbel** — host montuje projekt i `karmazyn.*`.

---

## Narzędzia

```text
karmazyn> :tool
karmazyn> :tool whoami
```

26/28 w smoke; `top` / `nano` tylko ręcznie.

---

## Bramka 1.0

```bash
python software/test_lua_release.py
# RELEASE GATE OK  karmazyn_lua 1.0.0
```

---

## Status

| | |
|--|--|
| **1.0.0** | stabilny gość + host API 1.x + tools |
| **2.0** | ewentualne breaking w kontraktach |
| **Nie jest** | pełna Lua 5.5 / ambient Uniks |

Archiwum ksh → `archiwum/`.
