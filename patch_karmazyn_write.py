with open('karmazyn.py', 'r') as f:
    content = f.read()

# Fix bits8 extraction from 64 to 15. The problem is hashlib.sha256(raw).digest()[:8] which is 8 bytes = 64 bits.
# So bits8 has shape (64,). And we are trying to put it into vec[:15].
# Let's just slice bits8 to 15: `bits8[:15]`

content = content.replace("vec[:15] = bits8.astype(np.int64)", "vec[:15] = bits8[:15].astype(np.int64)")

with open('karmazyn.py', 'w') as f:
    f.write(content)
