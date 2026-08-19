# testy/ — testy Pythona (prawo / golden / kubity)

Z katalogu repo:

```powershell
python -m unittest discover -s testy -p "test_*.py" -q
python testy/test_substrate.py
python testy/test_substrate_compat.py -v
python testy/test_qubit.py
python testy/test_phi_composition.py
python testy/test_hrr.py
python testy/test_lisp_golden.py   # Python Store vs karmazyn_shell (ten sam lisp_golden.txt)
```

| Plik | Co |
|------|----|
| `test_substrate.py` | prawo T×reach (Python Store, golden) |
| `test_substrate_compat.py` | Python ↔ Rust |
| `test_hrr.py` | HRR (numpy; skip bez numpy) |
| `test_qubit.py` | minister kubitów |
| `test_phi_composition.py` | φ 8.1 / 8.4 |
| `lisp_golden.txt` | przenośny korpus mini-Lisp (nie Rust, nie Python) |
| `test_lisp_golden.py` | ten korpus na obu jądrach + porównanie 1:1 |

Host / Lua (nie tu): `software/test_*.py`, `LUA/_run_tests.py`.  
Rust: `cargo test` w `native/` i `toolchain/kcc`.
