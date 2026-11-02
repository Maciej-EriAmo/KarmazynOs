# testy/ — testy Pythona (ministrowie, historia, kubity)

Prawo T×reach jest w `cargo test` crate `native/karmazyn_substrate`.

Z katalogu repo:

```powershell
python -m unittest discover -s testy -p "test_*.py" -q
python testy/test_substrate.py          # historia; nie jest bramką prawa
python testy/test_substrate_compat.py -v
python testy/test_qubit.py
python testy/test_phi_composition.py
python testy/test_hrr.py
python testy/test_lisp_golden.py   # korpus na open_store i na shellu
```

| Plik | Co |
|------|----|
| `test_substrate.py` | historia S1; nie jest bramką prawa |
| `test_substrate_compat.py` | `open_store` jest native; `backend=python` odmawia |
| `test_hrr.py` | HRR (numpy; skip bez numpy) |
| `test_qubit.py` | minister kubitów |
| `test_phi_composition.py` | φ 8.1 / 8.4 |
| `test_bubble_integrity.py` | odcisk HMAC bąbla w jądrze; BubbleFS 1.1: MAC treści, bez bąbla tożsamości, eksport jawny tylko za zgodą; archiwum odrzuca jawny rekord i manifest bez HMAC |
| `test_identity_store.py` | identity.bin v3 (DPAPI / hasło / jawny, migracja v2); session.soul bez p2s i jawnej treści |
| `test_crimson_resonance.py` | ten sam `_p2s` otwiera uścisk (próg 0.8); obcy `_p2s` milczy; macierz phi_space zostaje słownikiem |
| `lisp_golden.txt` | przenośny korpus mini-Lisp (nie Rust, nie Python) |
| `test_lisp_golden.py` | ten korpus na `open_store` i na shellu |

Host / Lua (nie tu): `software/test_*.py`, `LUA/_run_tests.py`.  
Rust: `cargo test` w `native/` i `toolchain/kcc`.
