# Plan domknięcia luk (karmazyn_lua → bliżej PUC-Rio)

**Cel:** domknąć rozbieżności z planu 1.1 **bez** C modules, ambient FS, bytecode, zmiany fizyki jądra.

## Zakres (wykonanie w tym PR)

| Faza | Zakres | Status |
|------|--------|--------|
| **A** | `debug.getinfo/getlocal/setlocal/getupvalue/setupvalue` + kontrakt | **DONE** |
| **A** | `coroutine.isyieldable`, `coroutine.close` | **DONE** |
| **B** | `collectgarbage("step")` + testy weak/`__gc` (już w silniku) | **DONE** |
| **C** | `string.dump` **zabronione**; golden patterns/format (już mocne) | **DONE** |
| **D** | `puc_subset/` runner + paczka testów | **DONE** |

## Poza zakresem (świadomie)

- C API / userdata / `package.loadlib`
- `io` na FS, `os.execute`, `dofile`
- `string.dump` / `load b` w gościu
- pełny `debug.sethook` / `getregistry`
- diff `kernel/` (fizyka T×reach)

## DoD

1. unit: nowe testy A/B/C  
2. `kombajn_run.py` FAIL=0  
3. `puc_subset_run.py` PASS  
4. brak ambient escape w `debug.*`

## Architektura ramek (A)

`_call_stack`: lista dictów `{name, what, fn, scope, source}` zamiast samych stringów.  
Traceback czyta `name`; getinfo/getlocal — pełny rekord.
