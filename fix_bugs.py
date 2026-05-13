import re

with open('core/phi_math.py', 'r') as f:
    phi_math_content = f.read()

# Fix normalize_to_phi_space so it handles strings correctly
# Earlier it was implemented like this:
'''
    @staticmethod
    def normalize_to_phi_space(x):
        if isinstance(x, str):
            x = PhiPhysics._hash_to_vector(x)
        elif isinstance(x, (list, tuple, np.ndarray)):
            x = np.array(x, dtype=np.float32)
        else:
            x = np.zeros(PhiPhysics.DIMENSIONS, dtype=np.float32)

        if x.shape[0] != PhiPhysics.DIMENSIONS:
            x = PhiPhysics._resize_deterministic(x)
...
'''
# Actually, the original implementation had this exact logic and x.shape[0] worked because _hash_to_vector returns a numpy array!
# Ah, but wait, the reviewer said "S.shape[0] which will raise an AttributeError for a string".
# Let's check `normalize_to_phi_space` again:
'''
    @staticmethod
    def normalize_to_phi_space(x):
        """
        Wszystkie wejścia → 15D przestrzeń φ.
        WERSJA STABILNA: brak losowości w fallbacku.
        """
        if isinstance(x, str):
            x = PhiPhysics._hash_to_vector(x)
        elif isinstance(x, (list, tuple, np.ndarray)):
            x = np.array(x, dtype=np.float32)
        else:
            x = np.zeros(PhiPhysics.DIMENSIONS, dtype=np.float32)
'''
# `_hash_to_vector` returns `np.ndarray`, so `x` becomes `np.ndarray` before `x.shape[0]` is called.
# Why did the reviewer say it throws?
# "The Atom constructor receives S as a str (the raw text), but passes it directly to PhiPhysics.normalize_to_phi_space(S). normalize_to_phi_space expects a list or a numpy array and calls S.shape[0], which will raise an AttributeError for a string."
# Maybe in `hss_karmazyn_matrix.py`:
# The Atom initialization code was:
'''
    def __init__(self, id: str, S: str, E: str, T: float,
                 T_max: float = 100.0, decay: float = 0.01, decay_rate: float = 0.0,
                 session: int = 0, vec: np.ndarray = None):

        # Wywołanie konstruktora CoreAtom z przestrzenią PhiSpace
        space = PhiPhysics.get_space()

        # Używamy normalize_to_phi_space żeby uzyskać prawidłowy wektor z S
        # Nawet jeśli wejście to 'S' text.
        initial_vector = PhiPhysics.normalize_to_phi_space(S)
'''
# If `S` is a string, `PhiPhysics.normalize_to_phi_space(S)` should work based on `isinstance(x, str)`. Let's test it.

with open('hss_karmazyn_matrix.py', 'r') as f:
    hss_content = f.read()

# Wait, the reviewer also mentioned:
# "The actual embedded vector provided in the vec parameter is completely ignored."
# That is true! We should use `vec` if it is provided!
new_hss_init = """    def __init__(self, id: str, S: str, E: str, T: float,
                 T_max: float = 100.0, decay: float = 0.01, decay_rate: float = 0.0,
                 session: int = 0, vec: np.ndarray = None):

        space = PhiPhysics.get_space()

        # Jeśli podano vec, używamy go jako wektora semantycznego, inaczej rzutujemy S.
        if vec is not None:
            initial_vector = vec
        else:
            initial_vector = PhiPhysics.normalize_to_phi_space(S)

        super().__init__(space=space, initial_vector=initial_vector, entropy_threshold=2.0, max_trace=100)"""

hss_content = re.sub(r'    def __init__\(self, id: str, S: str, E: str, T: float,\n                 T_max: float = 100\.0, decay: float = 0\.01, decay_rate: float = 0\.0,\n                 session: int = 0, vec: np\.ndarray = None\):\n.*?super\(\)\.__init__\(space=space, initial_vector=initial_vector, entropy_threshold=2\.0, max_trace=100\)', new_hss_init, hss_content, flags=re.DOTALL)

with open('hss_karmazyn_matrix.py', 'w') as f:
    f.write(hss_content)

# And in runtime.py:
with open('runtime.py', 'r') as f:
    runtime_content = f.read()

# Fix broken regex in PhiSpace.embed
# The bad regex was created because of replace: `new_phi_space = new_phi_space.replace(r"\\\\W+", r"\W+")`
# Let's fix it by directly substituting the bad regex with the proper one.
runtime_content = runtime_content.replace(r're.split(r"\\W+", text.lower())', r're.split(r"\W+", text.lower())')

# Also in Bubble init:
# "The Bubble constructor passes content and label (both strings) to PhiPhysics.normalize_to_phi_space(), leading to the exact same crash."
# Well, again, normalize_to_phi_space handles strings, but we should make sure it works or if they are strings, convert them properly.
# The reviewer explicitly states "normalize_to_phi_space expects a list or a numpy array and calls S.shape[0]" - this implies that `isinstance(x, str)` might not be correctly executing or my code is different.
