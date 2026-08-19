# karmazyn_lisp — gość na szwach substratu

Port `software/karmazyn_exec.py`. **Nie** drugi Store.

| Szw | Python | Tu |
|-----|--------|----|
| montaż | `eval_line(str) -> str` + `.env` | to samo |
| zmienne | atom, `metadata["v"]` | atom: token + **payload na atomie** (GC + snapshot) |
| scope | `Bubble` + parent | `bubble_new` / `lookup` |
| P6 closure | `env_of(closure) -> bubble` | `register_env_of("guest", …)` |
| ramka | temp `set_root` w `_apply` | to samo |

Shell tylko montuje: linia `(` → `eval_line`.
