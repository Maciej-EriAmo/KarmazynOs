with open('runtime.py', 'r') as f:
    content = f.read()

content = content.replace("_PHI_DIM = 64", "_PHI_DIM = 15")
with open('runtime.py', 'w') as f:
    f.write(content)

with open('karmazyn.py', 'r') as f:
    content = f.read()

content = content.replace("def __init__(self, n_sessions=1, dim=64, seed=42):", "def __init__(self, n_sessions=1, dim=15, seed=42):")
with open('karmazyn.py', 'w') as f:
    f.write(content)

with open('hss_karmazyn_matrix.py', 'r') as f:
    content = f.read()

content = content.replace("def __init__(self, dim: int = 64", "def __init__(self, dim: int = 15")
content = content.replace("np.zeros(64, dtype=np.float32)", "np.zeros(15, dtype=np.float32)")
with open('hss_karmazyn_matrix.py', 'w') as f:
    f.write(content)
print("dimensions patched")
