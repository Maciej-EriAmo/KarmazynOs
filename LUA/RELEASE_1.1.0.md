# Release checklist — karmazyn_lua **1.1.x** (production guest)

> Aktualna patch: **1.1.1** (P0 GC bloków + eval_line).

## Cel

Domyślny gość skryptowy KarmazynOS na poziomie **produkcyjnym 1.1.0**:
sandbox, host API, debug subset, bramka CI — **bez** C modules / ambient FS / bytecode.

## Checklista

| # | Zadanie | Status |
|---|---------|--------|
| 1 | Wersja pakietu `__version__ = 1.1.0` | [x] |
| 2 | README / CHANGELOG spójne z 1.1.0 | [x] |
| 3 | Host `karmazyn._VERSION` = 1.1.0 (surface 1.x) | [x] |
| 4 | Runtime `error()`: linia + chunk w tracebacku | [x] |
| 5 | Testy golden weak / `__gc` | [x] |
| 6 | Dokument kontraktu skryptów `CONTRACT_1.1.md` | [x] |
| 7 | Bramka `release_1_1.py` (unit + kombajn + puc + opcjonalnie host) | [x] |
| 8 | Monorepo `test_lua_release.py` akceptuje 1.1.x | [x] |
| 9 | Bramka zielona lokalnie | [x] |

## Poza 1.1.0 (świadomie)

- C API / userdata / `package.loadlib`
- ambient FS, `os.execute`, `dofile`
- `string.dump` / load binary
- pełny `debug.sethook` / `getregistry`
- pełny suite `lua-tests` PUC
- pełne hologramy / PCA

## Uruchomienie bramki

```bash
cd LUA
python release_1_1.py

# monorepo
python software/test_lua_release.py
```

## DoD

1. `python release_1_1.py` → exit 0  
2. kombajn FAIL=0  
3. puc_subset FAIL=0  
4. unit OK  
5. Dokumenty wskazują **1.1.0**
