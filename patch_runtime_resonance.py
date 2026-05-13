import re

with open('runtime.py', 'r') as f:
    content = f.read()

# Zmień logikę z list na przestrzeń rezonansu (resonance) w pętli `step` SanctuaryRuntime
# Obecna pętla `step` w `SanctuaryRuntime` robi m.in.: `for atom, event in self.matrix.step():`
# Pętla matrix.step() powiadamia o decay/tomb.
# User: "Zamiast zarządzać listami obiektów, runtime zarządza "przestrzenią", w której Atomy wchodzą w rezonans."

# Znajdźmy metodę consolidate_to_bubble w runtime.py
old_consolidate = """    def consolidate_to_bubble(self, atom, bubble):
        core = bubble.get_core_vector()

        result = PhiPhysics.snell_refraction(
            atom.S,
            core,
            bubble.density
        )

        if not result["penetrates"]:
            return {
                "status": "reflected",
                "atom": atom.id,
                "reason": "phase_mismatch",
                "coherence": result["coherence"]
            }

        bubble.absorb(atom)
        return {
            "status": "absorbed",
            "atom": atom.id
        }"""

new_consolidate = """    def consolidate_to_bubble(self, atom, bubble):
        # Nowy model: używamy rezonansu zamiast list/warunków statycznych
        # Rezonans: jedyna operacja komunikacji między bytami.
        from core.phi_math import PhiPhysics
        tau = 0.75 # próg rezonansu

        # Jeśli rezonują ze sobą w nowej geometrii S^14
        if bubble.resonates_with(atom, tau):
            bubble.absorb(atom)
            # Aktualizacja logiki predykcyjnej WORKSPACE
            bubble.update_psi([atom])
            return {
                "status": "absorbed",
                "atom": atom.id
            }

        return {
            "status": "reflected",
            "atom": atom.id,
            "reason": "phase_mismatch",
            "coherence": float(np.dot(PhiPhysics._space.normalize(atom.S), PhiPhysics._space.normalize(bubble.get_core_vector())))
        }"""

content = content.replace(old_consolidate, new_consolidate)

with open('runtime.py', 'w') as f:
    f.write(content)
print("Consolidate resonance patched")
