# kernel_python — zarchiwizowane jądro CPython (golden)

**To nie jest król.** Prawo T×reach w runtime = Rust (`native/karmazyn_substrate`).

Tu leży dawny `kernel/`:
- `karmazyn_substrate.py` — Python Store (referencja / golden)
- `karmazyn_atom.py` / `atomstore` / `hrr`
- `karmazyn_kernel.py` — fasada
- `karmazyn_backend.py` — `open_store` (szew native|python)

Import: `karmazyn_paths.ensure_import_paths()` albo `PYTHONPATH=…/archiwum/kernel_python`.

Product: `KARMAZYN_SUBSTRATE=native`. Python Store tylko z `ALLOW` (testy golden).
