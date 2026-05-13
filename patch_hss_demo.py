with open('hss_demo.py', 'r') as f:
    content = f.read()

content = content.replace("N = 64          # wymiar wektora", "N = 15          # wymiar wektora")

with open('hss_demo.py', 'w') as f:
    f.write(content)
