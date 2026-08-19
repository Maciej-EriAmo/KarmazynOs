# Host bez CPythona — jak zdjąć skórę

**Status:** living · **Data:** 2026-08-19  
**Cel:** „pełny system jak go odpalasz” **nie** wymaga `python`.

Dziś jądro i `karmazyn_shell` są w Rust. Padka to **launcher** (`karmazyn.cmd` wołał `python boot.py`) oraz goście (Lua/Lisp/Studio) napisane w CPythonie.

---

## Co już jest (H0)

| Start | Co robi | Python |
|-------|---------|--------|
| `karmazyn.cmd` / `Karmazyn.bat` **1** | `karmazyn_shell.exe` | **nie** |
| `karmazyn.cmd --python` / menu **3** | `software/karmazyn_boot.py` | tak, opcjonalnie |
| `karmazyn_native.cmd` | szuka exe (prefix / release / debug) | nie |

Zbuduj shell:

```powershell
.\native\bootstrap_from_scratch.ps1 -SkipC
# albo
cd native\karmazyn_shell && cargo build --release
```

---

## Mapa braków (to, czego native shell jeszcze nie jest)

Python boot to nie tylko REPL na Store. To też:

| H | Co | Stan |
|---|----|------|
| **H0** | Launcher = native shell | ✅ ta sesja |
| **H1** | Raport startu `[ OK ]` usług po stronie shell | native ma `version`/`stats`, nie sekwencję boot |
| **H2a** | Gość **mini-Lisp** na szwach Store | ✅ crate `karmazyn_lisp` (jak `karmazyn_exec.py`) |
| **H2** | Gość Lua **bez** CPythona | `LUA/` nadal CPython — mlua **albo** Lua zostaje `--python` |
| **H3** | `lua_bin/*` jako narzędzia native | dziś `karmazyn.*` host API w Pythonie |
| **H4** | Studio SDL | zostaje ministrem na hoście z Pythonem **albo** osobny crate |
| **H5** | Kubity / φ | minister Python — na żądanie, nie warunek startu |

**Pełny odpowiednik dzisiejszego boot.py** = H0+H1+H2.  
**Uczciwy „system wstaje bez Pythona”** = H0 (już): Store + shell + save/load.

Nie portujemy CPythona do Rusta. Portujemy **szew startu**. Lua to osobna decyzja (mlua), nie warunek króla.

Mini-Lisp = ten sam szew co w Pythonie, w Rust:

| Szw | `karmazyn_exec.py` | `karmazyn_lisp` |
|-----|--------------------|-----------------|
| montaż | `eval_line` + `.env` | to samo |
| zmienne | atom + `metadata["v"]` | atom: token + **payload na atomie** (vacuum + KSUB_SNAP v2) |
| GC | `env_of(closure)→bąbel`, ramka = temp root | `register_env_of("guest")` |
| shell | boot montuje ewaluator | linia `(` → `eval_line` |

```text
k$ (define x 10)
10
```

---

## Klient Python (nie nośnik)

Python ma być **klientem ABI**, jak `ksub_client.c`:

| | Boot / Store drop-in | Klient |
|--|----------------------|--------|
| Plik | `software/karmazyn_boot.py`, `karmazyn_substrate_native.py` | `native/ksub_client.py` |
| Rola | skóra hosta / drop-in Store | woła `ksub_*`, nie implementuje prawa |
| Start systemu | opcjonalny `--python` | nigdy nie jest launcherem |

```powershell
python native/ksub_client.py
```

`karmazyn_substrate_native.py` zostaje mostem dla starej skóry. Nowy kod Pythona na substracie idzie przez `KSub` / C ABI, nie przez `from karmazyn_kernel import Store`.

---

## Zakaz

1. Nie wołać `python` z `karmazyn.cmd` bez `--python`.  
2. Nie udawać, że native shell = Lua REPL.  
3. Nie wciągać Studio do bramki „wstaje bez Pythona”.
