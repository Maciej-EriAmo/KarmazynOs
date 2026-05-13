import re
with open('karmazyn.py', 'r') as f:
    content = f.read()

content = content.replace("def __init__(self, dim=64, n_sessions=1, seed=42):", "def __init__(self, dim=15, n_sessions=1, seed=42):")
content = content.replace("def __init__(self, dim=64, n_sessions=1, seed=42, auto_cleanup_interval=50):", "def __init__(self, dim=15, n_sessions=1, seed=42, auto_cleanup_interval=50):")
content = content.replace("vec[:64]", "vec[:15]")
# what is N?
# likely 64 or 512, need to check N definition.
with open('karmazyn.py', 'w') as f:
    f.write(content)
print("done")
