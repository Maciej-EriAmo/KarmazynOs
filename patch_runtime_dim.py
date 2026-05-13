with open('runtime.py', 'r') as f:
    content = f.read()

# Change dim usage in PhiSpace to self.space.n
content = content.replace("vec = np.zeros(self.dim, dtype=np.float32)", "vec = np.zeros(self.space.n, dtype=np.float32)")
content = content.replace("v = np.random.default_rng(seed).standard_normal(self.dim).astype(np.float32)", "v = np.random.default_rng(seed).standard_normal(self.space.n).astype(np.float32)")

# What about self.dim in the init?
# def __init__(self, dim: int = _PHI_DIM):
# self.dim = dim

with open('runtime.py', 'w') as f:
    f.write(content)
print("done")
