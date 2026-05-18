#!/usr/bin/env python3
"""
karmazyn_comm.py — Termodynamiczny menadżer komunikacji v1.0.0
==============================================================
Obsługuje SMS i połączenia przez Termux API.
Kontakty i wiadomości jako Atomy Φ — ważne stygnią wolniej,
spam wypada przez Vacuum Decay.

Wymaga: Termux:API (termux-sms-list, termux-sms-send,
                     termux-telephony-call, termux-contact-list)
        numpy, karmazyn.py, hss_karmazyn_matrix.py, hss_demo.py
"""

import os
import sys
import json
import math
import time
import hashlib
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple

try:
    from karmazyn import KarmazynOS, DELTA_T_BASE
except ImportError:
    print("Błąd: nie znaleziono karmazyn.py")
    sys.exit(1)

VERSION = "1.0.0"

# ─── Konfiguracja termiczna ───────────────────────────────────────────────────

T_CONTACT_KNOWN   = 8.0   # znany kontakt — wysoka temperatura
T_CONTACT_UNKNOWN = 3.0   # nieznany numer
T_MSG_INCOMING    = 6.0   # przychodzący SMS
T_MSG_SENT        = 4.0   # wysłany SMS (potwierdzenie)
T_CALL_MISSED     = 7.0   # nieodebrane — pilne
T_CALL_ANSWERED   = 3.0   # odebrane — mniej pilne po odebraniu
T_SPAM_THRESHOLD  = 1.5   # poniżej → prawdopodobny spam
DECAY_SPAM        = 0.3   # szybki rozpad dla spamu
DECAY_NORMAL      = 0.05  # normalny rozpad
POLL_INTERVAL     = 30    # sekund między sprawdzeniem nowych SMS


# ─── Termux helpers ───────────────────────────────────────────────────────────

def _run(cmd: List[str], timeout=10) -> Tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError:
        return -2, "", f"nie znaleziono: {cmd[0]}"

def termux_sms_list(limit=50) -> List[dict]:
    code, out, err = _run(["termux-sms-list", "-l", str(limit), "-t", "inbox"])
    if code != 0 or not out:
        return []
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return []

def termux_sms_send(number: str, message: str) -> bool:
    code, _, err = _run(["termux-sms-send", "-n", number, message])
    return code == 0

def termux_call(number: str) -> bool:
    code, _, _ = _run(["termux-telephony-call", number])
    return code == 0

def termux_contact_list() -> List[dict]:
    code, out, _ = _run(["termux-contact-list"])
    if code != 0 or not out:
        return []
    try:
        return json.loads(out)
    except:
        return []

def termux_notify(title: str, content: str, id: int = 1):
    _run(["termux-notification", "--title", title, "--content", content, "--id", str(id)])


# ─── Model danych ─────────────────────────────────────────────────────────────

@dataclass
class Contact:
    number: str
    name: str = ""
    label: str = ""          # etykieta w Φ
    known: bool = False
    msg_count: int = 0
    last_seen_epoch: int = 0

@dataclass
class Message:
    id: str
    number: str
    body: str
    timestamp: str
    direction: str           # "in" | "out"
    label: str = ""          # etykieta w Φ
    replied: bool = False
    score: float = 0.0


# ─── PhiScheduler ─────────────────────────────────────────────────────────────

class PhiScheduler:
    """
    Kolejka komend sterowana temperaturą Φ.
    Zamiast FIFO — najgorętszy atom wykonuje się pierwszy.
    """
    def __init__(self, ko: KarmazynOS):
        self.ko = ko
        self._queue: Dict[str, callable] = {}  # label → callable

    def enqueue(self, cmdline: str, action: callable, init_T: float = DELTA_T_BASE):
        label = self.ko.write(cmdline)
        # ustaw temperaturę manualnie przez atom
        a = self.ko.phi._mx.get_atom(label)
        if a is not None:
            a['T'] = init_T
        self._queue[label] = action
        return label

    def next(self) -> Optional[Tuple[str, callable]]:
        best_label, best_T = None, -1.0
        for lbl in self._queue:
            a = self.ko.phi._mx.get_atom(lbl)
            if a is not None:
                if a['T'] > best_T:
                    best_label, best_T = lbl, a['T']
        if best_label:
            action = self._queue.pop(best_label)
            return best_label, action
        return None

    def run_all(self, max_steps=20):
        executed = 0
        while executed < max_steps:
            item = self.next()
            if item is None:
                break
            label, action = item
            try:
                action()
            except Exception as e:
                print(f"  [SCHED] Błąd akcji '{label[:30]}': {e}")
            executed += 1
        return executed

    @property
    def size(self):
        return len(self._queue)


# ─── KarmazynComm ─────────────────────────────────────────────────────────────

class KarmazynComm:
    def __init__(self, dim=64, seed=42):
        self.ko = KarmazynOS(dim=dim, seed=seed)
        self.sched = PhiScheduler(self.ko)
        self.contacts: Dict[str, Contact] = {}   # number → Contact
        self.messages: Dict[str, Message] = {}   # id → Message
        self._seen_ids: set = set()
        self._running = False
        self._lock = threading.Lock()
        print(f"\n  KarmazynComm v{VERSION} — Termodynamiczny Menadżer Komunikacji")
        print(f"  T_vacuum = {self.ko.phi.t_vacuum():.4f} bit\n")

    # ── Kontakty ─────────────────────────────────────────────────────────────

    def load_contacts(self):
        contacts = termux_contact_list()
        loaded = 0
        for c in contacts:
            name   = c.get('name', '')
            number = c.get('number', '').replace(' ', '').replace('-', '')
            if not number:
                continue
            label = self._add_contact(number, name, known=True)
            loaded += 1
        print(f"  [KONTAKTY] Załadowano {loaded} kontaktów do Φ")
        return loaded

    def _add_contact(self, number: str, name: str = "", known: bool = False) -> str:
        if number in self.contacts:
            return self.contacts[number].label
        content = f"kontakt:{number}:{name}"
        init_T  = T_CONTACT_KNOWN if known else T_CONTACT_UNKNOWN
        label   = self.ko.write(content)
        for a in self.ko.phi._mx.atoms:
            if a['label'] == label:
                a['T'] = init_T
                break
        c = Contact(number=number, name=name, label=label, known=known,
                    last_seen_epoch=self.ko.phi.epoch)
        self.contacts[number] = c
        return label

    def get_contact_name(self, number: str) -> str:
        c = self.contacts.get(number)
        if c and c.name:
            return c.name
        return number

    def contact_temperature(self, number: str) -> float:
        c = self.contacts.get(number)
        if not c:
            return 0.0
        for a in self.ko.phi._mx.atoms:
            if a['label'] == c.label:
                return a['T']
        return 0.0

    # ── Wiadomości ────────────────────────────────────────────────────────────

    def ingest_sms(self, sms_list: List[dict]) -> int:
        new_count = 0
        for sms in sms_list:
            sid    = str(sms.get('_id', hashlib.md5(
                         str(sms).encode()).hexdigest()[:12]))
            if sid in self._seen_ids:
                continue
            self._seen_ids.add(sid)

            number = sms.get('number', '').replace(' ', '')
            body   = sms.get('body', '')
            ts     = sms.get('received', '')

            if not number or not body:
                continue

            # upewnij się że mamy kontakt
            name   = self.get_contact_name(number)
            c_lbl  = self._add_contact(number, name)
            c      = self.contacts[number]
            c.msg_count += 1
            c.last_seen_epoch = self.ko.phi.epoch

            # ocena spamu przez Φ
            spam_score = self._spam_score(number, body)
            is_spam    = spam_score < T_SPAM_THRESHOLD

            # temperatura wiadomości
            init_T = T_MSG_INCOMING
            if is_spam:
                init_T = T_SPAM_THRESHOLD * 0.8
            elif c.known:
                init_T = T_MSG_INCOMING + 1.0

            # zapisz do Φ
            content = f"sms_in:{number}:{name}:{body[:200]}"
            label   = self.ko.write(content)
            for a in self.ko.phi._mx.atoms:
                if a['label'] == label:
                    a['T'] = init_T
                    break

            msg = Message(id=sid, number=number, body=body,
                          timestamp=ts, direction="in",
                          label=label, score=init_T)
            self.messages[sid] = msg

            if is_spam:
                self.ko.mark_bubble_for_decay(label, rate=DECAY_SPAM)
                print(f"  [SPAM?] {number}: {body[:50]}")
            else:
                # powiadomienie termux
                termux_notify(
                    f"SMS od {name or number}",
                    body[:100],
                    id=abs(hash(sid)) % 10000
                )
                print(f"  [SMS↓] {name or number}: {body[:60]} (T={init_T:.1f})")
                # podniesienie temperatury kontaktu
                for a in self.ko.phi._mx.atoms:
                    if a['label'] == c_lbl:
                        a['T'] = min(a['T'] + 1.5, T_CONTACT_KNOWN * 1.5)
                        break

            new_count += 1

        return new_count

    def _spam_score(self, number: str, body: str) -> float:
        spam_keywords = [
            'wygraj', 'nagroda', 'kliknij', 'promocja', 'oferta',
            'win', 'prize', 'click', 'free', 'offer', 'urgent',
            'http://', 'bit.ly', 'tinyurl'
        ]
        body_lower = body.lower()
        hits = sum(1 for kw in spam_keywords if kw in body_lower)
        # znany kontakt → nie spam
        if number in self.contacts and self.contacts[number].known:
            return T_CONTACT_KNOWN
        return T_CONTACT_UNKNOWN - hits * 0.5

    # ── Priorytety przez Φ ────────────────────────────────────────────────────

    def priority_inbox(self, k=10) -> List[Message]:
        """Zwraca wiadomości posortowane przez score Φ (nie chronologicznie)."""
        scored = []
        for msg in self.messages.values():
            if msg.direction != "in":
                continue
            results = self.ko.recall(f"{msg.number} {msg.body[:50]}", k=3)
            score   = results[0]['score'] if results else 0.0
            msg.score = score
            scored.append(msg)
        scored.sort(key=lambda m: m.score, reverse=True)
        return scored[:k]

    def suggest_reply(self, msg: Message) -> Optional[str]:
        """Szuka podobnych starych wiadomości żeby zasugerować odpowiedź."""
        results = self.ko.recall(msg.body, k=5)
        for r in results:
            lbl = r['label']
            # szukaj wysłanych wiadomości z podobnym kontekstem
            for m in self.messages.values():
                if m.label == lbl and m.direction == "out":
                    return m.body
        return None

    # ── Akcje ─────────────────────────────────────────────────────────────────

    def send_sms(self, number: str, message: str, priority: float = DELTA_T_BASE):
        def _action():
            ok = termux_sms_send(number, message)
            name = self.get_contact_name(number)
            if ok:
                content = f"sms_out:{number}:{name}:{message[:200]}"
                label   = self.ko.write(content)
                mid     = hashlib.md5((number + message + str(time.time())).encode()).hexdigest()[:12]
                self.messages[mid] = Message(
                    id=mid, number=number, body=message,
                    timestamp=str(int(time.time())), direction="out",
                    label=label, replied=True, score=T_MSG_SENT
                )
                print(f"  [SMS↑] → {name or number}: {message[:60]}")
                # konsoliduj wysłane do bąbli (trwała pamięć)
                self.ko.consolidate(label)
            else:
                print(f"  [BŁĄD] Nie wysłano SMS do {number}")

        self.sched.enqueue(f"send_sms:{number}:{message[:30]}", _action, init_T=priority)

    def call(self, number: str, priority: float = T_CALL_MISSED):
        def _action():
            name = self.get_contact_name(number)
            ok   = termux_call(number)
            if ok:
                print(f"  [CALL] → {name or number}")
            else:
                print(f"  [BŁĄD] Nie można zadzwonić do {number}")

        self.sched.enqueue(f"call:{number}", _action, init_T=priority)

    def mark_replied(self, msg_id: str):
        msg = self.messages.get(msg_id)
        if msg:
            msg.replied = True
            # stygnięcie po odpowiedzi
            for a in self.ko.phi._mx.atoms:
                if a['label'] == msg.label:
                    a['T'] *= 0.5
                    break

    # ── Polling ───────────────────────────────────────────────────────────────

    def poll_once(self) -> int:
        sms_list = termux_sms_list(limit=50)
        new = self.ingest_sms(sms_list)
        self.ko.step()
        return new

    def start_polling(self, interval: int = POLL_INTERVAL):
        self._running = True
        def _loop():
            while self._running:
                with self._lock:
                    try:
                        new = self.poll_once()
                        if new:
                            executed = self.sched.run_all()
                    except Exception as e:
                        print(f"  [POLL] Błąd: {e}")
                time.sleep(interval)
        t = threading.Thread(target=_loop, daemon=True)
        t.start()
        print(f"  [POLL] Daemon uruchomiony (co {interval}s)")
        return t

    def stop_polling(self):
        self._running = False

    # ── Stats ─────────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        s = self.ko.stats()
        total_msgs  = len(self.messages)
        unread      = sum(1 for m in self.messages.values()
                          if m.direction == "in" and not m.replied)
        return {
            **s,
            "contacts":       len(self.contacts),
            "messages_total": total_msgs,
            "unread":         unread,
            "queue_size":     self.sched.size,
        }

    def print_stats(self):
        s = self.stats()
        print(f"\n  KarmazynComm | Epoka: {s['epoch']}")
        print(f"  Kontakty: {s['contacts']}  |  Wiadomości: {s['messages_total']}")
        print(f"  Nieprzeczytane: {s['unread']}  |  Kolejka: {s['queue_size']}")
        print(f"  Atomy Φ: {s['atoms_phi']}  |  Bąble: {s['bubbles']}")
        print(f"  Temperatura Φ: {s['temperature']:.3f}  |  T_vacuum: {s['t_vacuum']:.4f}")


# ─── Shell komunikacyjny ──────────────────────────────────────────────────────

class CommShell:
    def __init__(self):
        self.comm = KarmazynComm()
        self.comm.load_contacts()

    def print_help(self):
        print("""
  KarmazynComm Shell — komendy:
  ─────────────────────────────────────────────────────
  poll               — sprawdź nowe SMS (jednorazowo)
  daemon [sekundy]   — uruchom polling w tle
  inbox [k]          — priorytetowa skrzynka (Φ-sorted)
  contacts [query]   — lista kontaktów / szukaj
  send <numer> <msg> — wyślij SMS przez scheduler
  call <numer>       — zadzwoń przez scheduler
  run                — wykonaj kolejkę (najgorętsze wpierw)
  reply <msg_id>     — oznacz jako odczytane
  hot                — kontakty o najwyższej temperaturze
  stats              — statystyki systemu
  step [n]           — przesuń czas (chłodzenie Φ)
  save [path]        — zapisz stan
  load [path]        — wczytaj stan
  help               — ta pomoc
  exit               — wyjście
  ─────────────────────────────────────────────────────
  Wszystko inne → przekazane do /bin/sh
        """)

    def execute(self, cmdline: str):
        import shlex
        cmdline = cmdline.strip()
        if not cmdline or cmdline.startswith('#'):
            return
        try:
            parts = shlex.split(cmdline)
        except ValueError as e:
            print(f"Błąd składni: {e}")
            return
        cmd  = parts[0].lower()
        args = parts[1:]

        try:
            if cmd == "poll":
                new = self.comm.poll_once()
                print(f"  Nowych wiadomości: {new}")

            elif cmd == "daemon":
                interval = int(args[0]) if args else POLL_INTERVAL
                self.comm.start_polling(interval)

            elif cmd == "inbox":
                k    = int(args[0]) if args else 10
                msgs = self.comm.priority_inbox(k=k)
                if not msgs:
                    print("  Brak wiadomości.")
                    return
                print(f"\n  {'#':<3} {'Od':<20} {'Treść':<45} {'Score':>6}")
                print("  " + "─" * 78)
                for i, m in enumerate(msgs, 1):
                    name    = self.comm.get_contact_name(m.number)
                    replied = "✓" if m.replied else " "
                    print(f"  {i:<3} {name[:18]:<20} {m.body[:43]:<45} {m.score:>6.2f} {replied}")
                    print(f"      id:{m.id}  {m.timestamp[:16]}")
                print()

            elif cmd == "contacts":
                query = " ".join(args) if args else ""
                items = list(self.comm.contacts.values())
                if query:
                    q = query.lower()
                    items = [c for c in items
                             if q in c.name.lower() or q in c.number]
                items.sort(key=lambda c: self.comm.contact_temperature(c.number), reverse=True)
                print(f"\n  {'Nazwa':<25} {'Numer':<15} {'T':>6} {'SMS':>4}")
                print("  " + "─" * 55)
                for c in items[:20]:
                    T = self.comm.contact_temperature(c.number)
                    k = "★" if c.known else " "
                    print(f"  {k}{c.name[:23]:<25} {c.number[:13]:<15} {T:>6.2f} {c.msg_count:>4}")
                print()

            elif cmd == "send":
                if len(args) < 2:
                    print("Użycie: send <numer> <wiadomość>")
                    return
                number = args[0]
                msg    = " ".join(args[1:])
                self.comm.send_sms(number, msg)
                print(f"  Dodano do kolejki Φ → {number}")

            elif cmd == "call":
                if not args:
                    print("Użycie: call <numer>")
                    return
                self.comm.call(args[0])
                print(f"  Dodano połączenie do kolejki Φ → {args[0]}")

            elif cmd == "run":
                n = self.comm.sched.run_all()
                print(f"  Wykonano {n} akcji z kolejki Φ")

            elif cmd == "reply":
                if not args:
                    print("Użycie: reply <msg_id>")
                    return
                self.comm.mark_replied(args[0])
                print(f"  Oznaczono {args[0]} jako odczytane")

            elif cmd == "hot":
                items = list(self.comm.contacts.values())
                items.sort(key=lambda c: self.comm.contact_temperature(c.number), reverse=True)
                print("\n  Najgorętsze kontakty:")
                for c in items[:8]:
                    T    = self.comm.contact_temperature(c.number)
                    bar  = "█" * int(T) + "░" * max(0, 10 - int(T))
                    print(f"  {c.name or c.number:<25} {bar} {T:.2f}")
                print()

            elif cmd == "stats":
                self.comm.print_stats()

            elif cmd == "step":
                n = int(args[0]) if args else 1
                self.comm.ko.step(n)
                print(f"  Epoka: {self.comm.ko.phi.epoch}")

            elif cmd == "save":
                path = args[0] if args else "./comm_data"
                self.comm.ko.save(path)

            elif cmd == "load":
                path = args[0] if args else "./comm_data"
                self.comm.ko.load(path)

            elif cmd in ("exit", "quit"):
                print("  Do zobaczenia.")
                sys.exit(0)

            elif cmd == "help":
                self.print_help()

            else:
                # ── fallback do systemu ──────────────────────────────────────
                if cmd == "cd":
                    target = args[0] if args else os.path.expanduser("~")
                    try:
                        os.chdir(target)
                        print(f"  {os.getcwd()}")
                    except FileNotFoundError:
                        print(f"  Nie znaleziono: {target}")
                else:
                    try:
                        result = subprocess.run(
                            parts,
                            capture_output=False,
                            env=os.environ
                        )
                    except FileNotFoundError:
                        print(f"  Nieznana komenda: '{cmd}'. Wpisz 'help'.")
                    except KeyboardInterrupt:
                        print()

        except KeyboardInterrupt:
            print()
        except Exception as e:
            print(f"  Błąd: {e}")

    def run(self):
        print("  Wpisz 'help' po listę komend.\n")
        while True:
            try:
                line = input("comm> ").strip()
                self.execute(line)
            except KeyboardInterrupt:
                print("\n  Użyj 'exit' aby wyjść.")
            except EOFError:
                print("\n  exit")
                break


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="KarmazynComm — Termodynamiczny menadżer komunikacji")
    parser.add_argument("--poll",   action="store_true", help="Jednorazowy poll i wyjście")
    parser.add_argument("--daemon", type=int, metavar="SEC", help="Daemon polling co SEC sekund")
    parser.add_argument("--inbox",  action="store_true", help="Pokaż inbox i wyjście")
    args = parser.parse_args()

    if args.poll:
        comm = KarmazynComm()
        comm.load_contacts()
        new = comm.poll_once()
        print(f"Nowych: {new}")
        msgs = comm.priority_inbox(k=5)
        for m in msgs:
            print(f"  {m.number}: {m.body[:60]}  (score={m.score:.2f})")

    elif args.daemon:
        comm = KarmazynComm()
        comm.load_contacts()
        comm.start_polling(args.daemon)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nZatrzymano daemon.")

    elif args.inbox:
        comm = KarmazynComm()
        comm.load_contacts()
        comm.poll_once()
        msgs = comm.priority_inbox(k=10)
        for i, m in enumerate(msgs, 1):
            print(f"{i}. {m.number}: {m.body[:70]}  (score={m.score:.2f})")

    else:
        CommShell().run()
