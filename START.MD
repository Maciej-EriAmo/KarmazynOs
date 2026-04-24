# KarmazynOS — Quick Start

**Time to read: 5 minutes**
**Requirements: Python 3.10+, numpy, 10 MB disk space**

---

## Installation (2 minutes)

```bash
# 1. Clone the repository
git clone https://github.com/Maciej-EriAmo/KarmazynOs
cd KarmazynOs

# 2. Install dependencies
pip install numpy --break-system-packages

# 3. Launch the shell
python shell.py
```

You should see:

```
Karmazyn Shell v1.1.0 | KarmazynOS v1.1.1
Type 'help' to see available commands, 'exit' to quit.
ksh>
```

---

## First Steps (3 minutes)

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

### 3. Move it to long-term memory (bubble)

```
ksh> consolidate $LAST
[CONSOLIDATION] 'atom_a261722b' → bubble_4bf1eb7b01a1
```

### 4. Create an idea from several bubbles

```
ksh> write "Code readability is crucial"
ksh> consolidate $LAST
ksh> idea "Python philosophy" atom_a261722b atom_22cb7dc5
[IDEA] Created 'idea_Python_philosophy_0_a1b2c3' from 2 bubbles.
```

### 5. Generate a new thought from the idea

```
ksh> gen idea_Python_philosophy_0_a1b2c3 "how to write readable code" 0.5
Generated Φ atom: gen_idea_Python_philosophy_0_a1b2c3_1 (temp=0.5)
```

### 6. Check system stats

```
ksh> stats
KarmazynOS v1.1.1 | Epoch: 0
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

## Or use the web Studio

```bash
python studio.py
# Open http://localhost:8080 in your browser
# On Termux: termux-open-url http://localhost:8080
```

Studio gives you a three-panel interface: Φ atoms with temperature visualization on the left, a Python editor with live execution in the center, and bubbles on the right. You can run Python code directly in the KarmazynOS context (`ko`, `phi`, `bubbles`, `np` available).

---

## Essential Commands

| Command | Action |
|---------|--------|
| `write "text"` | Add new information to Φ |
| `recall "query"` | Search memory |
| `consolidate <label>` | Move atom to long-term memory |
| `idea <topic> <labels>` | Create an idea from bubbles |
| `gen <idea> <prompt>` | Generate a new thought from an idea |
| `spawn <idea> <prompt> --consolidate` | Generate and save permanently |
| `step 10` | Advance time by 10 epochs |
| `stats` | Show system statistics |
| `save ./directory` | Save the entire state |
| `load ./directory` | Load a saved state |
| `help` | Show all commands |

---

## Persistence formats

KarmazynOS supports two persistence formats:

**Default** (`save`/`load` in shell):
```
my_state/
    meta.json        # epoch, p2s key, version
    hss_matrix.npz   # atom vectors
    phi_sem.npz      # semantic vectors
    bubbles.pkl      # bubble store
    holograms.json   # hologram data
```

**Soul format** (recommended, more robust):
```python
from soul_store import save_soul, load_soul
save_soul(ko, "./my_state")
load_soul(ko, "./my_state")
# Creates: session.soul (JSONL) + vectors.npz
```

---

## Project structure

```
KarmazynOs/
├── karmazyn.py              # Core kernel
├── hss_demo.py              # Security daemon (Ring-LWE)
├── hss_karmazyn_matrix.py   # Atom matrix
├── shell.py                 # ksh shell
├── studio.py                # Web Studio
├── soul_store.py            # .soul persistence
├── bubblefs.py              # BubbleFS exchange format
├── karmazyn_comm.py         # Communication manager
├── karmazyn_ui/             # Design Language
│   ├── tokens.py
│   ├── states.py
│   └── renderer.py
├── static/
│   ├── karmazyn.css
│   └── karmazyn_tokens.js
├── how_to.md                # Full user guide (PL)
└── how_to_en.md             # Full user guide (EN)
```

---

## FAQ

**Q: Does data disappear when I close the shell?**
A: Yes, unless you save with `save`. Use `load` to restore on next launch. The `.soul` format is more robust across Python versions.

**Q: What is temperature?**
A: A measure of freshness in working memory Φ. High = recently used, low = being forgotten. Atoms below `T_vacuum` undergo Vacuum Decay and are removed automatically.

**Q: Why do I need holograms?**
A: They are generative structures — from a group of bubbles, they create new semantically related thoughts. `gen` and `spawn` use them as creative starting points.

**Q: What is the cryptographic model?**
A: KarmazynOS uses Ring-LWE post-quantum cryptography for prism isolation. Each bubble has a key derived from the session's Φ² — data is unreadable without the session history. See [HSS Paper](https://doi.org/10.5281/zenodo.19548693).

---

**Done. You are now the operator of your own thermodynamic memory.**
