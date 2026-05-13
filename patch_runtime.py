import re

with open('runtime.py', 'r') as f:
    content = f.read()

new_phi_space = """class PhiSpace:
    def __init__(self, dim: int = _PHI_DIM):
        self.dim = dim
        self.epoch = 0
        self._sem: Dict[str, np.ndarray] = {}
        self._rc: Dict[str, int] = {}
        from core.phi_math import PhiPhysics
        self.space = PhiPhysics.get_space()

    def embed(self, text: str) -> np.ndarray:
        # Use simple string replace to avoid re template escape issues in python re.sub
        tokens = [w for w in re.split(r"\\\\W+", text.lower()) if len(w) > 1]
        if not tokens:
            tokens = [text[:8] if text else "empty"]
        vec = np.zeros(self.dim, dtype=np.float32)
        for tok in set(tokens):
            seed = int(hashlib.md5(tok.encode()).hexdigest(), 16) % (2 ** 32)
            v = np.random.default_rng(seed).standard_normal(self.dim).astype(np.float32)
            vec += v
        return self.space.normalize(vec)

    def register(self, label: str, text: str):
        self._sem[label] = self.embed(text)
        self._rc[label] = 0

    def add_vector(self, label: str, vec: np.ndarray):
        self._sem[label] = self.space.normalize(vec)
        self._rc[label] = 0

    def search(self, query: str, candidates: List[str], k: int = 5) -> List[Tuple[str, float]]:
        q = self.embed(query)
        scores = []
        for lbl in candidates:
            v = self._sem.get(lbl)
            if v is None:
                continue
            # Używamy nowej metryki, metryka zwraca 0 dla identycznych, więc musimy to odwrócić na similarity
            sim = 1.0 - (self.space.metric(q, v) / 2.0) # Normalizujemy do [0, 1]
            scores.append((lbl, sim))
        scores.sort(key=lambda x: x[1], reverse=True)
        for lbl, _ in scores[:k]:
            self._rc[lbl] = self._rc.get(lbl, 0) + 1
        return scores[:k]

    def get(self, label: str) -> Optional[np.ndarray]:
        return self._sem.get(label)

    def remove(self, label: str):
        self._sem.pop(label, None)
        self._rc.pop(label, None)"""
new_phi_space = new_phi_space.replace(r"\\\\W+", r"\W+")

start_idx = content.find("class PhiSpace:")
end_idx = content.find("class Bubble:", start_idx)

if start_idx != -1 and end_idx != -1:
    new_content = content[:start_idx] + new_phi_space + "\n\n\n# =====================================================================\n# BUBBLE / HOLOGRAM / AGENT\n# =====================================================================\n\n" + content[end_idx:]
    with open('runtime.py', 'w') as f:
        f.write(new_content)
    print("Patched PhiSpace in runtime.py")
else:
    print("Could not find start/end indices")
