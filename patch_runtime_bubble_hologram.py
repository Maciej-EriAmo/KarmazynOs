import re

with open('runtime.py', 'r') as f:
    content = f.read()

# Replace Hologram class with one inheriting from core
# Replace Bubble class with one inheriting from core
# But runtime has specific methods: `Bubble.liveliness`, `Bubble.get_core_vector`, `Bubble.absorb`
# and `Hologram.liveliness`.
# We should just update the runtime's local classes to inherit and adapt, or just use core logic.
# Wait, user said: "Zmień runtime.py tak, aby jego główna pętla operowała na instancji PhiSpace zaimportowanej z nowego rdzenia. Mechanizm: Zamiast zarządzać listami obiektów, runtime zarządza "przestrzenią", w której Atomy wchodzą w rezonans."

new_classes = """from karmazyn_core import Hologram as CoreHologram, Bubble as CoreBubble, BubbleMode

class Bubble(CoreBubble):
    def __init__(self, label: str, content: str, immortal: bool = False):
        from core.phi_math import PhiPhysics
        self.label = label
        self.content = content
        self.immortal = immortal
        self.density = 1.0

        space = PhiPhysics.get_space()
        # Utwórz prowizoryczny hologram dla phi1
        vecs = [PhiPhysics.normalize_to_phi_space(content)]
        phi1 = CoreHologram(space, vecs)
        phi2_vector = PhiPhysics.normalize_to_phi_space(label)

        super().__init__(space=space, phi1=phi1, phi2_vector=phi2_vector, theta=3.0, mode=BubbleMode.WORKSPACE)

    def get_core_vector(self):
        # Maintain compatibility
        from core.phi_math import PhiPhysics
        return PhiPhysics.normalize_to_phi_space(self.content)

    def absorb(self, atom):
        self.content = f"{self.content} {atom._S_raw if hasattr(atom, '_S_raw') else atom.S} {atom.E}".strip()

    def liveliness(self, runtime) -> float:
        atom = runtime.get_atom(self.label)
        if atom is None:
            return 0.0
        return max(0.0, min(1.0, atom.T / atom.T_max))


class Hologram(CoreHologram):
    def __init__(self, hid: str, topic: str, proto: np.ndarray,
                 generators: List[np.ndarray], weights: List[float],
                 atom_labels: List[str], epoch: int):
        self.id = hid
        self.topic = topic
        self.proto = proto
        self.generators = generators
        self.weights = weights
        self.atom_labels = atom_labels
        self.epoch_created = epoch

        from core.phi_math import PhiPhysics
        space = PhiPhysics.get_space()

        # Inicjalizacja CoreHologram
        # Jeżeli brakuje nam trajektorii z doświadczeń, użyjmy prota i generatorów
        vecs = [proto] + generators if generators else [proto]
        super().__init__(space, vecs)

    def liveliness(self, current_epoch: int) -> float:
        return math.exp(-0.001 * max(0, current_epoch - self.epoch_created))
"""

start_idx = content.find("class Bubble:")
end_idx = content.find("class Agent:", start_idx)

if start_idx != -1 and end_idx != -1:
    new_content = content[:start_idx] + new_classes + "\n\n" + content[end_idx:]
    with open('runtime.py', 'w') as f:
        f.write(new_content)
    print("Patched Bubble and Hologram in runtime.py")
else:
    print("Could not find Bubble/Hologram classes")
