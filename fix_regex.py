with open('runtime.py', 'r') as f:
    content = f.read()

# Let's just find the bad line and replace it manually.
content = content.replace(r're.split(r"\\W+", text.lower())', r're.split(r"\W+", text.lower())')

with open('runtime.py', 'w') as f:
    f.write(content)
