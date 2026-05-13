import re

with open('hss_karmazyn_matrix.py', 'r') as f:
    content = f.read()

# Replace the Atom class definition
new_atom_class = """from karmazyn_core import Atom as CoreAtom
from core.phi_math import PhiPhysics

class Atom(CoreAtom):
    \"\"\"
    Atom termodynamiczny KarmazynOS dziedziczący po karmazyn_core.Atom.

    Zarządza trajektorią w przestrzeni S^14 i posiada ewolucję termodynamiczną.
    \"\"\"
    # Nie używamy __slots__ ze względu na dziedziczenie,
    # chyba że w CoreAtom też zastosujemy __slots__, ale łatwiej to pominąć w Pythonie.

    def __init__(self, id: str, S: str, E: str, T: float,
                 T_max: float = 100.0, decay: float = 0.01, decay_rate: float = 0.0,
                 session: int = 0, vec: np.ndarray = None):

        # Wywołanie konstruktora CoreAtom z przestrzenią PhiSpace
        space = PhiPhysics.get_space()

        # Używamy normalize_to_phi_space żeby uzyskać prawidłowy wektor z S
        # Nawet jeśli wejście to 'S' text.
        initial_vector = PhiPhysics.normalize_to_phi_space(S)

        super().__init__(space=space, initial_vector=initial_vector, entropy_threshold=2.0, max_trace=100)

        self.id        = id
        self.S         = S
        self.E         = E
        self.T         = float(T)
        self.T_max     = float(T_max)
        self.decay     = float(decay)
        self.decay_rate = float(decay_rate)
        self.age       = 0
        self.session   = session
        self.splamiony = False
        # Zachowujemy _vec jako alias na current_pos (używamy aktualnej pozycji na sferze)
        self._vec      = self.current_pos
        self.state     = _classify(self.T)

    def __getitem__(self, key):
        if key == 'label': return self.id
        if key == 'S': return self.current_pos
        if key == 'T': return self.T
        if key == 'session': return self.session
        raise KeyError(key)

    def __setitem__(self, key, value):
        if key == 'T': self.T = float(value)
        elif key == 'S':
             # Aktualizacja wektora semantycznego
             delta = value - self.current_pos
             self.move(delta)
             self._vec = self.current_pos
        else: raise KeyError(f"Cannot set {key} via dict interface")

    def get(self, key, default=None):
        try: return self[key]
        except KeyError: return default

    def __repr__(self):
        return f"Atom({self.id!r} T={self.T:.1f} state={self.state})"
"""

# Find the Atom class and replace it
atom_pattern = re.compile(r'class Atom:.*?def __repr__\(self\):\n        return f"Atom\(\{self\.id!r\} T=\{self\.T:\.1f\} state=\{self\.state\}\)"\n', re.DOTALL)
content = atom_pattern.sub(new_atom_class, content)

with open('hss_karmazyn_matrix.py', 'w') as f:
    f.write(content)
