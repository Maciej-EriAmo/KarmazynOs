
# KarmazynOS — Quick Start

**Time to read: 5 minutes**  
**Requirements: Python 3.10+, pip, 10 MB disk space**

---

## 📦 Installation (2 minutes)

```bash
# 1. Clone the repository
git clone https://github.com/your-username/karmazyn-os
cd karmazyn-os

# 2. Install dependencies
pip install numpy

# 3. Launch the shell
python shell.py
```

You should see:

```
Karmazyn Shell v1.1.0 | KarmazynOS v1.1.0
Type 'help' to see available commands, 'exit' to quit.
ksh>
```

---

## 🧪 First Steps (3 minutes)

### 1. Write a thought

```
ksh> write "Python is a high-level programming language"
Saved: atom_a261722b
```

### 2. Recall it

```
ksh> recall "programming language"
1. [phi] atom_a261722b (score=0.823)
```

### 3. Move it to long-term memory

```
ksh> consolidate atom_a261722b
[CONSOLIDATE] 'atom_a261722b' → bubble_4bf1eb7b01a1
```

### 4. Create an idea from several bubbles

```
ksh> write "Code readability is crucial"
Saved: atom_22cb7dc5

ksh> consolidate atom_22cb7dc5
[CONSOLIDATE] 'atom_22cb7dc5' → bubble_ed64874ca798

ksh> idea "Python philosophy" atom_a261722b atom_22cb7dc5
[IDEA] Created 'idea_Python_philosophy_42_a1b2c3' from 2 bubbles.
```

### 5. Generate a new thought from the idea

```
ksh> gen idea_Python_philosophy_42_a1b2c3 "how to write readable code" 0.5
Generated atom Φ: gen_idea_Python_philosophy_42_a1b2c3_44 (temp=0.5)
```

### 6. Check system stats

```
ksh> stats
KarmazynOS v1.1.0 | Epoch: 0
Φ Temperature: 4.85 | T_vacuum: 5.7187
Φ Atoms: 3 | Bubbles: 2 (decaying: 0)
Ideas: 1 | Bias: 1.432
```

### 7. Save your state

```
ksh> save ./my_state
State saved to ./my_state
```

---

## 🎮 Essential Commands

| Command | Action |
|---------|--------|
| `write "text"` | Add new information |
| `recall "query"` | Search memory |
| `consolidate <label>` | Move to long-term memory |
| `idea <topic> <labels>` | Create an idea from bubbles |
| `gen <idea> <prompt>` | Generate a new thought from an idea |
| `spawn <idea> <prompt> --consolidate` | Generate and save permanently |
| `step 10` | Advance time by 10 epochs |
| `stats` | Show system statistics |
| `save ./directory` | Save the entire state |
| `load ./directory` | Load a previously saved state |
| `help` | Show all commands |

---

## 📂 Project Structure

```
karmazyn-os/
├── karmazyn.py              # Main kernel
├── shell.py                 # KSH shell
├── hss_demo.py              # Security daemon
├── hss_karmazyn_matrix.py   # HSS matrix
├── README.md                # General documentation
├── HOWTO.md                 # Full user guide
├── ARCHITECTURE.md          # Architecture description
└── examples/
    └── demo.karm            # Demo script
```

---

## 🚀 What Next?

- Read [HOWTO.md](how_to_en.md) — complete user guide.
- Read [ARCHITECTURE.md](docs/ARCHITECTURE.md) — understand the mathematics.
- Run `ksh> run examples/demo.karm` — see an automated demo.
- Experiment with `gen` and `spawn` — watch the system create new thoughts.

---

## ❓ FAQ

**Q: Does data disappear when I close the shell?**  
A: Yes, unless you save with `save`. Use `load` to restore on the next launch.

**Q: What is temperature?**  
A: A measure of "freshness" in working memory Φ. High = frequently used, low = being forgotten.

**Q: Why do I need holograms?**  
A: They are generators — from a group of bubbles, they create new, similar thoughts. You don't need to remember everything — you just need the idea.

**Q: Is this secure?**  
A: KarmazynOS uses post-quantum cryptography (Ring‑LWE). More in [POSTQUANTUM.md](POSTQUANTUM.md).

---

**Done. You are now the operator of your own thermodynamic memory.** 
