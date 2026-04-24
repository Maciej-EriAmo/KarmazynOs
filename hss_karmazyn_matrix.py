import numpy as np

class HSSKarmazynMatrix:
    def __init__(self, dim=64, n_sessions=1, lambd=0.1, seed=42):
        self.dim = dim
        self.atoms = []
        self.time = 0
        self.lambd = lambd
        self.rng = np.random.default_rng(seed)

    def add_atom_vector(self, label, topic, vector, init_T, session=0):
        self.atoms.append({
            'label': label,
            'topic': topic,
            'S': vector.copy(),
            'T': init_T,
            'session': session
        })

    def step(self):
        self.time += 1
        new_atoms = []
        for a in self.atoms:
            a['T'] *= (1 - self.lambd)
            if a['T'] > 0.01:
                new_atoms.append(a)
        self.atoms = new_atoms
        return len(self.atoms)

    def save(self, path):
        np.savez(path, atoms=self.atoms, time=self.time, allow_pickle=True)

    def load(self, path):
        data = np.load(path, allow_pickle=True)
        self.atoms = data['atoms'].tolist()
        self.time = int(data['time'])