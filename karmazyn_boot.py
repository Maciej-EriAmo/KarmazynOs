#!/usr/bin/env python3
"""
karmazyn_boot.py — punkt startowy samodzielnego runtime KarmazynOS (v0.3)
=========================================================================
Maciej Mazur, Warsaw 2026

Po boocie: PROMPT WYKONAWCZY. Wpisujesz kod (mini-Lisp) — liczy sie.
  - linia kodu              -> warstwa wykonawcza (karmazyn_exec)
  - linia ':...'            -> komenda systemu (OS meta)

Start RAPORTUJE uslugi na ekran: [ OK ]/[WARN]/[FAIL] per usluga, z czasem.
Kolor tylko na terminalu (na potoku/do pliku — czyste tagi). Awaria uslugi
jest zgloszona jako [FAIL] i przerywa start czysto, bez surowego traceback.

Zmienne z `define` to atomy w bablu-korzeniu -> zyja pod REACH-GC. Zero
zaleznosci zewnetrznych (dziala bez numpy).

  python3 karmazyn_boot.py          # interaktywny prompt
  python3 karmazyn_boot.py --demo   # skryptowa sesja

SZEW MONTAZU: boot oczekuje obiektu z `eval_line(str)->str`. Bogatszy front-end
(np. karmazyn_scheme) wpina sie tak samo.
"""

import os
import sys
import threading
import time

from karmazyn_kernel import Store, kernel_info

try:
    import readline
    _HAS_READLINE = True
except Exception:
    _HAS_READLINE = False


# ─────────────────────────────────────────────────────────────────────────────
# Raport startu uslug
# ─────────────────────────────────────────────────────────────────────────────
class BootLog:
    """Log startu na ekran. [ OK ]/[WARN]/[FAIL], kolor tylko gdy stdout to TTY."""

    _COLOR = {"ok": "32", "warn": "33", "fail": "31"}   # zielony/zolty/czerwony

    def __init__(self, stream=None, color=None):
        self.stream = stream or sys.stdout
        self.color = (self.stream.isatty() if color is None else color)
        self.failed = False

    def _tag(self, code):
        label = {"ok": " OK ", "warn": "WARN", "fail": "FAIL"}[code]
        if self.color:
            return f"[\x1b[1;{self._COLOR[code]}m{label}\x1b[0m]"
        return f"[{label}]"

    def _line(self, code, name, detail, ms):
        t = f"  ({ms:.1f} ms)" if ms is not None else ""
        d = f" — {detail}" if detail else ""
        print(f"  {self._tag(code)} {name}{d}{t}", file=self.stream)

    def ok(self, name, detail="", ms=None):
        self._line("ok", name, detail, ms)

    def warn(self, name, detail="", ms=None):
        self._line("warn", name, detail, ms)

    def fail(self, name, detail="", ms=None):
        self.failed = True
        self._line("fail", name, detail, ms)


def _ms(t0):
    return (time.perf_counter() - t0) * 1000.0


# ─────────────────────────────────────────────────────────────────────────────
def mount_evaluator(store):
    """Montuje warstwe wykonawcza na Store. Tu wpina sie karmazyn_scheme, gdy bedzie.
    Kontrakt: obiekt z metoda eval_line(str) -> str, ze zmiennymi w Store (reach-GC)."""
    import karmazyn_exec
    return karmazyn_exec.Evaluator(store, env_label="repl")


class KarmazynShell:
    """Prompt: kod -> warstwa wykonawcza; ':...' -> komendy systemu."""

    def __init__(self, store, evaluator, verbose_events=False):
        self.store = store
        self.ev = evaluator
        self.env = evaluator.env
        if verbose_events:
            store.events.on("vacuum_decay",
                            lambda a: print(f"  [GC] vacuum_decay: {a.id} ({a.E})"))

    def feed(self, line: str) -> str:
        line = line.strip()
        if not line:
            return ""
        if line.startswith(":"):
            return self._meta(line[1:].split())
        return self.ev.eval_line(line)

    def _meta(self, parts):
        if not parts:
            return ""
        cmd, args = parts[0].lower(), parts[1:]
        fn = getattr(self, f"_m_{cmd}", None)
        if fn is None:
            return f"nieznana komenda systemu: :{cmd}  (:help)"
        try:
            return fn(args)
        except (ValueError, IndexError) as e:
            return f"zly argument dla :{cmd}: {e}"
        except Exception as e:
            return f"blad :{cmd}: {type(e).__name__}: {e}"

    def _m_help(self, a):
        return ("KOD: (define x 10)  (+ x 5)  (if (> x 0) x 0)  (lambda (n) (* n n))  (begin ...)\n"
                "OS : :info | :stats | :tick [n] | :gc | :ls [stan] | :env | :find <q> | :new <S> <E> | :exit")

    def _m_info(self, a):
        i = kernel_info()
        return (f"KarmazynOS jadro v{i['version']}  D={i['vec_dim']}  "
                f"HRR={'on' if i['hrr_active'] else 'off (zero-dep)'}\n"
                f"prawo: {i['law']}")

    def _m_stats(self, a):
        return str(self.store.stats())

    def _m_tick(self, a):
        n = int(a[0]) if a and a[0].lstrip('-').isdigit() else 1
        before = self.store.stats()
        self.store.settle(n)
        after = self.store.stats()
        d_reaped = after["reaped"] - before["reaped"]
        d_total = before["total"] - after["total"]
        return f"tick x{n}: ubylo {d_total} atomow (zreapowano {d_reaped}); -> {after}"

    def _m_gc(self, a):
        before = self.store.stats()["reaped"]
        for _ in range(1000):
            r0 = self.store.stats()["reaped"]
            self.store.tick()
            if self.store.stats()["reaped"] == r0 and self.store.stats()["hot"] == 0:
                break
        reaped = self.store.stats()["reaped"] - before
        return f"vacuum: zreapowano {reaped} -> {self.store.stats()}"

    def _m_ls(self, a):
        state = a[0] if a else None
        atoms = self.store.atoms(state)
        if not atoms:
            return "(brak atomow)" + (f" w stanie {state}" if state else "")
        return "\n".join(f"  {x.id:4}  T={x.T:5.1f} {x.state:4}  S={x.S!r} E={x.E!r}"
                         for x in atoms)

    def _m_env(self, a):
        out = []
        b = self.env
        depth = 0
        while b is not None:
            names = ", ".join(b.bindings.keys()) or "(puste)"
            out.append(f"  {'  '*depth}{b.label}: {names}")
            b = b.parent
            depth += 1
        return "\n".join(out)

    def _m_find(self, a):
        if not a:
            return "uzycie: :find <zapytanie>"
        hits = self.store.resonance(" ".join(a), k=5)
        if not hits:
            return "brak rezonansu (HRR/numpy nieaktywne)"
        return "\n".join(f"  {sim:.3f}  {aid}" for sim, aid in hits)

    def _m_new(self, a):
        if not a:
            return "uzycie: :new <S> [E]"
        S = a[0]; E = " ".join(a[1:]) if len(a) > 1 else ""
        atom = self.store.atom_new(S, E)
        return f"sierota {atom.id}  S={S!r} E={E!r} (niezwiazana)"

    def _m_exit(self, a):
        return "__EXIT__"


def _scheduler(store, interval, stop):
    while not stop.wait(interval):
        store.tick()


class BootError(RuntimeError):
    """Start przerwany — usluga krytyczna nie wstala (zgloszona jako [FAIL])."""


def boot(verbose_events=False, log=None):
    """Sekwencja startowa z raportem uslug. Zwraca (store, shell).
    Awaria uslugi krytycznej -> [FAIL] + BootError (czysto, bez surowego traceback)."""
    log = log or BootLog()
    print("=" * 60)
    print("  KarmazynOS — sekwencja startowa")
    print("=" * 60)

    # 1. fasada jadra (musi zaladowac sie samodzielnie)
    t = time.perf_counter()
    try:
        i = kernel_info()
    except Exception as e:
        log.fail("fasada jadra", f"{type(e).__name__}: {e}")
        raise BootError("fasada jadra nie wstala") from e
    log.ok("fasada jadra", f"v{i['version']} D={i['vec_dim']}", _ms(t))
    if i["hrr_active"]:
        log.ok("HRR (wektory)", "aktywne (numpy)")
    else:
        log.warn("HRR (wektory)", "wylaczone — brak numpy (tryb zero-dep)")

    # 2. substrat (Store + reach-GC)
    t = time.perf_counter()
    try:
        store = Store(thermal=True)
    except Exception as e:
        log.fail("substrat (Store)", f"{type(e).__name__}: {e}")
        raise BootError("substrat nie wstal") from e
    log.ok("substrat (Store, reach-GC)", f"prawo: {i['law']}", _ms(t))

    # 3. warstwa wykonawcza (montaz: env_of + korzen)
    t = time.perf_counter()
    try:
        evaluator = mount_evaluator(store)
    except Exception as e:
        log.fail("warstwa wykonawcza", f"{type(e).__name__}: {e}")
        raise BootError("warstwa wykonawcza nie wstala") from e
    wired = (evaluator.env in store.roots)
    log.ok("warstwa wykonawcza", f"env_of wpiete, korzen={'tak' if wired else 'NIE'}", _ms(t))

    # 4. shell
    t = time.perf_counter()
    shell = KarmazynShell(store, evaluator, verbose_events=verbose_events)
    log.ok("shell", "prompt gotowy", _ms(t))

    return store, shell


def _setup_history():
    if not _HAS_READLINE:
        return
    import atexit
    histfile = os.path.expanduser("~/.karmazyn_history")
    try:
        if os.path.exists(histfile):
            readline.read_history_file(histfile)
        atexit.register(readline.write_history_file, histfile)
    except Exception:
        pass


def repl(interval=2.0):
    log = BootLog()
    try:
        store, shell = boot(verbose_events=True, log=log)
    except BootError as e:
        print(f"\n  start przerwany: {e}")
        sys.exit(1)

    # uslugi REPL (osobno, bo zalezne od trybu interaktywnego)
    _setup_history()
    if _HAS_READLINE:
        log.ok("historia (readline)", "~/.karmazyn_history")
    else:
        log.warn("historia", "readline niedostepne — bez historii linii")

    stop = threading.Event()
    threading.Thread(target=_scheduler, args=(store, interval, stop), daemon=True).start()
    log.ok("scheduler termiczny", f"tick co {interval:g}s (tlo)")

    print("  " + "-" * 56)
    print("  start zakonczony. Wpisz kod albo ':help'.\n")
    try:
        while True:
            out = shell.feed(input("karmazyn> "))
            if out == "__EXIT__":
                break
            if out:
                print(out)
    except (EOFError, KeyboardInterrupt):
        print()
    finally:
        stop.set()
    print("Zamykanie KarmazynOS.")


def demo():
    store, shell = boot(verbose_events=True)
    print("  " + "-" * 56)
    print("  start zakonczony (tryb demo).\n")
    script = [
        ":info",
        "(define x 10)", "(define y (+ x 5))", "(+ x y)",
        "(if (> y x) (* x y) 0)",
        "(define keep 123)",
        ":new sierota orphan-bez-wiazania",
        ":ls", ":tick 200", ":ls tomb", "keep", "(+ keep x)",
        "(define counter (lambda () (begin (define n 0) (lambda () (begin (set! n (+ n 1)) n)))))",
        "(define c (counter))", "(c)", "(c)", ":tick 100", "(c)",
        ":env", ":stats", ":exit",
    ]
    for line in script:
        print(f"\nkarmazyn> {line}")
        out = shell.feed(line)
        if out == "__EXIT__":
            break
        if out:
            print(out)
    print("\n[demo] warstwa wykonawcza dziala; zmienne zyja pod reach-GC, nie pod temperatura.")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    else:
        repl()
