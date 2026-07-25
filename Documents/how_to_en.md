
# 📘 KarmazynOS — User Guide

**Version 1.0.0** (classic Φ write/recall model)  
**Runtime 2026 (boot + Lua):** → **[runtime_en.md](runtime_en.md)**

```bash
# Canonical 2026 — live interpreter
python karmazyn_boot.py
python karmazyn_boot.py --demo
```

Below: classic ksh guide (`write` / `recall`) — legacy under `archiwum/` in the monorepo.

---

KarmazynOS is a thermodynamic memory kernel — a system that remembers, recalls, forgets, and creates new ideas. It operates across three layers:

| Layer         | Physical State | Description |
|---------------|----------------|-------------|
| **Φ (Phi)**   | Plasma         | Working memory — information competes for attention and cools over time. |
| **Bubble**    | Solid          | Persistent memory — data is stored faithfully, but may gradually "fade" over time. |
| **Hologram**  | Field          | Idea — does not store specifics, but generates new variants. |

Classic UX: **Karmazyn Shell (ksh)** (archive). Runtime 2026: **`karmazyn_boot`** + Lua.

---

## 🚀 Getting Started (classic ksh)

Launch the shell (if present in your install / archive):

```bash
python shell.py
```

You will see the welcome message:

```
Karmazyn Shell v1.0 | KarmazynOS v1.0.0
Type 'help' to see available commands, 'exit' to quit.
ksh>
```

To list all commands:

```bash
ksh> help
```

---

## ✍️ Basic Memory Operations

### Adding Information to Φ

```bash
ksh> write "Python allows rapid prototyping"
Saved: atom_abc123
```

Every entry receives a unique label. The most recent label is stored in the `$LAST` variable.

### Recalling Information

```bash
ksh> recall "programming language"
1. [phi] atom_abc123 (score=0.823)
```

The system searches both Φ (working memory) and bubbles. Results are sorted by semantic relevance.

### Consolidation — Moving to Persistent Memory

```bash
ksh> consolidate $LAST
[CONSOLIDATION] 'atom_abc123' → bubble_xyz789
```

From now on, the information exists as a bubble — it will not disappear when Φ cools, though it may undergo slow decay.

---

## 🧠 Managing Bubbles

| Command      | Syntax                        | Description |
|--------------|-------------------------------|-------------|
| **decay**    | `decay <label> <rate>`        | Sets decay rate for the bubble (e.g. 0.05 = 5% per epoch) |
| **refresh**  | `refresh <label>`             | Resets the decay process — restores full vitality |
| **revoke**   | `revoke <label>`              | Invalidates the bubble (Warp Oblivion) — becomes unreadable |
| **reactivate** | `reactivate <label>`        | Reactivates the bubble back into Φ as a new atom |

**Examples:**

```bash
ksh> decay atom_abc123 0.05
ksh> refresh atom_abc123
ksh> revoke atom_abc123
ksh> reactivate atom_abc123
```

---

## 💡 Working with Ideas (Holograms)

### Creating an Idea

```bash
ksh> idea "Python philosophy" b1 b2 b3
[IDEA] Created 'idea_Python_philosophy_42_a1b2c3' from 3 bubbles.
```

An idea is a generative hologram — it does not store original content, but represents a space of possible variants.

### Generating a New Atom from an Idea

```bash
ksh> gen idea_Python_philosophy_42_a1b2c3 "code readability" 0.5
Generated Φ atom: gen_idea_Python_philosophy_42_a1b2c3_44 (temp=0.5)
```

- **prompt** — direction for generation  
- **temperature** — higher values increase creativity (default: 0.3)

### Spawn — Generate and Optionally Consolidate

```bash
ksh> spawn idea_Python_philosophy_42_a1b2c3 "performance" --consolidate
Created and consolidated bubble: spawn_idea_Python_philosophy_42_a1b2c3_45
```

### Rehydrating an Idea

```bash
ksh> rehydrate idea_Python_philosophy_42_a1b2c3
Rehydrated atoms: rehyd_idea_Python_philosophy_42_a1b2c3_0, rehyd_idea_Python_philosophy_42_a1b2c3_1, ...
```

---

## ⏳ Time Flow

KarmazynOS has an internal clock measured in **epochs**. Each epoch:

- Atoms in Φ cool down (lose temperature)
- Bubbles with decay lose vitality
- Every 50 epochs, revoked bubbles are automatically cleaned (GC)

To advance time:

```bash
ksh> step 10          # advance 10 epochs
ksh> step             # one epoch
```

---

## 📊 System Monitoring

```bash
ksh> stats
```

Example output:

```
KarmazynOS v1.0.0
Epoch: 52 | Φ Temperature: 3.21 | T_vacuum: 5.7187
Φ Atoms: 12 | Bubbles: 7 (decaying: 2)
Revoked Bubbles: 1 | Ideas (holograms): 2
Bubble Bias: 1.854
```

---

## 🧪 .karm Scripts

You can save sequences of commands in `.karm` files.

**Example `demo.karm`:**

```karm
write "KarmazynOS is a thermodynamic system"
consolidate $LAST
write "It uses three layers of memory"
idea "basics" $LAST
step 5
spawn idea_basics "architecture" --consolidate
stats
```

Run the script with:

```bash
ksh> run demo.karm
```

---

## 🔐 Agents (Advanced Feature)

Agents are separate entities with their own cryptographic keys that can read data through a secure Ring-LWE channel.

```bash
ksh> agent derive alice "data analysis" core in
Agent created: PID=101, session key (first 8): [23 145 ...]

ksh> agent read 101 atom_abc123 --bubble
```

> Note: Full agent support requires storing session keys. In the demo version, this feature may be limited.

---

## 📌 Shell Commands Summary

| Command                                 | Description |
|-----------------------------------------|-------------|
| `write <text>`                          | Add an atom to Φ |
| `recall <query>`                        | Search in Φ and bubbles |
| `consolidate <label>`                   | Move atom to a bubble |
| `reactivate <label>`                    | Reactivate bubble back to Φ |
| `revoke <label>`                        | Invalidate bubble |
| `decay <label> <rate>`                  | Set decay rate for bubble |
| `refresh <label>`                       | Reset bubble decay |
| `idea <topic> <list of labels>`         | Create a hologram (idea) |
| `ideas`                                 | List all ideas |
| `gen <idea_id> <prompt> [temp]`         | Generate Φ atom from idea |
| `spawn <idea_id> <prompt> [--consolidate]` | Generate and optionally consolidate |
| `rehydrate <idea_id>`                   | Rehydrate atoms from idea |
| `stats`                                 | Show system statistics |
| `step [n]`                              | Advance time by n epochs |
| `gc`                                    | Manual garbage collection of revoked bubbles |
| `run <file.karm>`                       | Execute a script |
| `help [command]`                        | Show help |
| `exit`                                  | Exit the shell |

---

## 🧭 KarmazynOS Philosophy

- Memory is not a warehouse — information has **temperature**, **vitality**, and can evolve.
- Ideas are not facts — holograms generate variants, they do not reproduce the past.
- Time flows — everything is subject to thermodynamics.

**With KarmazynOS you don’t just store data — you cultivate thoughts.**
```