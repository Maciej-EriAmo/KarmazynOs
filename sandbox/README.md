# Piaskownica KarmazynOs (enterprise kickoff)

Izolowane miejsce na eksperymenty **bez** psucia monorepo Product.

## Zasady

1. Kod Product (prawo Store) → **Z0** w `native/karmazyn_substrate` (nie tutaj).
2. Tutaj: skrypty, notatki, temporary Store, próby Studio/cmdline.
3. `sandbox/work/` jest w `.gitignore` — nie commitować śmieci sesji.
4. Przed scaleniem do `software/` / `kernel/`: gate + review.

## Bootstrap

```powershell
python sandbox/bootstrap_sandbox.py
```

Tworzy:

```
sandbox/work/
  README.md          # lokalna notatka sesji
  run_repl.ps1       # REPL z PYTHONPATH
  run_studio.ps1     # Studio
  run_gate.ps1       # odpal gate z roota
  experiments/       # Twoje pliki
```

## Start projektu (ta fala)

| Krok | Status |
|------|--------|
| Enterprise review wdrożona | tak — docs + gate + CI + boundary |
| Piaskownica | ten katalog |
| L1 Product host | w toku — po `gate_product` PASS na main |
| L2 ISO / GRUB | nie zaczynać przed L1 |

## Pierwsze eksperymenty (bezpieczne)

```powershell
cd sandbox/work
.\run_gate.ps1 -SkipLua
.\run_repl.ps1
# w REPL: :io   :hot   x=1
```

Eksperyment matrycy bez psucia bootu:

```python
# sandbox/work/experiments/heat_lab.py
import sys, os
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path[:0] = [ROOT, f"{ROOT}/software", f"{ROOT}/kernel", f"{ROOT}/native"]
os.environ["KARMAZYN_SUBSTRATE"] = "python"
from karmazyn_kernel import open_store
from karmazyn_io import attach_thermal, QueueIo
s = open_store(backend="python", thermal=True)
t = attach_thermal(s, QueueIo())
t.heat_input()
print(t.stats())
```
