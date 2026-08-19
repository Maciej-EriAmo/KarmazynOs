# Kubity w KarmazynOS

**Status:** minister amplitud · **nie** król · **nie** hardware  
**Kod:** `karmazyn_qubit.py` · testy: `testy/test_qubit.py`  
**Algebra φ (dokument v2.2):** `testy/test_phi_composition.py`

## Co to jest

`Reg(n)` trzyma wektor stanu `2^n` liczb zespolonych na CPU. Limit `n ≤ 8`.  
Bramki: `H X Y Z S T`, `phase`, `CNOT`, `SWAP`. Pomiar jednego / wszystkich.  
Entropia von Neumanna podukładu (`entropy(wires)`). Bloch przy `n=1`.

```python
from karmazyn_qubit import Reg, bell
r = bell()                 # (|00⟩+|11⟩)/√2
r.entropy((0,))            # ln 2
r.measure_all()            # tylko 00 albo 11
```

```powershell
python karmazyn_qubit.py --demo
python -m unittest discover -s testy -p "test_qubit.py" -v
```

## Czego to nie jest

- Nie jest komputerem kwantowym i nie bije klasycznego Pythona na 2ⁿ.
- Store / T / reach **nie liczą** amplitud.
- T nie jest dekoherencją `Reg`.
- Bind / HRR nie jest splątaniem (S = 0).
- Bąbel nie jest kubitem.

## Co substrat *może* zrobić przy kubitach

Obudowa, nie macierze: zapisać przepis obwodu, ziarno, histogram pomiarów; T jako kolejka (gorące eksperymenty vs zimne logi); `bind` przepisu z wynikiem.  
Most cienki: po `measure_all()` bitstring → atom.

## Testy z dokumentu φ (v2.2)

Sekwencja: **8.1 konieczny** → dopiero wtedy **8.4 dostateczny**. φ nie wolno wstawiać.

| Test | Pytanie | Werdykt |
|------|---------|---------|
| 8.1 | widmo N_τ spełnia λ²−λ−1=0? (wejście 0/1) | TAK; kontrola ℤ₂ nie |
| 8.2 | D_n z DP kanałów, rekurencja Fibonacci | TAK |
| 8.4 | przestrzeń fuzji 4×τ, S>0 generycznie | TAK w Hilbert; NIE na Store/HRR/T |

Podsumowanie dopisane do  
`Documents/Phi_Holografia_Kompozycja_Splatanie_KarmazynOS_v2.2 (1).docx` §11.

```powershell
python -m unittest discover -s testy -p "test_phi_composition.py" -v
```
