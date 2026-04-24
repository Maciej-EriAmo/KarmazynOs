import numpy as np
import json
import os


class HSSKarmazynMatrix:
    def __init__(self, dim=64, n_sessions=1, lambd=0.1, seed=42):
        self.dim = dim
        self.atoms = []
        self.time = 0
        self.lambd = lambd
        self.rng = np.random.default_rng(seed)

    def add_atom_vector(self, label, topic, vector, init_T, session=0):
        self.atoms.append({
            'label':   label,
            'topic':   topic,
            'S':       vector.copy(),
            'T':       init_T,
            'session': session,
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
        """
        Zapisuje do dwóch plików bez pickle:
          <base>.npz  — tablice numpy S i T
          <base>.json — metadane (etykiety, tematy, sesje, czas)
        """
        base = path.replace(".npz", "")

        if not self.atoms:
            np.savez(base + ".npz",
                     S=np.zeros((0, self.dim), dtype=np.float32),
                     T=np.zeros(0, dtype=np.float32))
            with open(base + ".json", "w") as f:
                json.dump({"time": self.time, "atoms": []}, f)
            return

        S = np.array([a["S"] for a in self.atoms], dtype=np.float32)
        T = np.array([a["T"] for a in self.atoms], dtype=np.float32)
        np.savez(base + ".npz", S=S, T=T)

        meta = {
            "time": self.time,
            "atoms": [
                {
                    "label":   a.get("label", ""),
                    "topic":   a.get("topic", ""),
                    "session": a.get("session", 0),
                }
                for a in self.atoms
            ]
        }
        with open(base + ".json", "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)

    def load(self, path):
        """
        Wczytuje z <base>.npz + <base>.json.
        Fallback do starego formatu pickle jesli brak .json.
        """
        base      = path.replace(".npz", "")
        npz_path  = base + ".npz"
        json_path = base + ".json"

        if not os.path.exists(npz_path):
            return

        if os.path.exists(json_path):
            data  = np.load(npz_path, allow_pickle=False)
            S_arr = data["S"]
            T_arr = data["T"]

            with open(json_path, "r", encoding="utf-8") as f:
                meta = json.load(f)

            self.time  = int(meta.get("time", 0))
            self.atoms = []
            for i, am in enumerate(meta.get("atoms", [])):
                if i >= len(S_arr):
                    break
                self.atoms.append({
                    "label":   am.get("label", f"atom_{i}"),
                    "topic":   am.get("topic", ""),
                    "S":       S_arr[i],
                    "T":       float(T_arr[i]),
                    "session": am.get("session", 0),
                })
        else:
            # fallback: stary format pickle
            data = np.load(npz_path, allow_pickle=True)
            self.atoms = data["atoms"].tolist()
            self.time  = int(data["time"])
