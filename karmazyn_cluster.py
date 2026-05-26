#!/usr/bin/env python3
"""
karmazyn_cluster.py — KarmazynOS HyperCluster v1.0
====================================================
Maciej Mazur, Warsaw 2026

Warstwa klastrowa KarmazynOS. Zamienia N węzłów KarmazynOS
w rozproszony superkomputer termodynamiczny.

Filozofia:
  Nie ma centralnego schedulera — fizyka phi-space Jest schedulerem.
  Gorące atomy migrują do zimnych węzłów (work stealing).
  Zimne atomy umierają naturalnie (TOMB = job done/expired).
  Rezonans między węzłami = wspólna przestrzeń obliczeniowa.

Prymitywy klastra:
  atom          → jednostka obliczeniowa (job/task)
  T (temp.)     → priorytet: wyższe T = pilniejsze zadanie
  thermal decay → naturalny timeout bez crona
  bubble        → checkpoint / wynik / batch job
  handshake     → dołączenie węzła (KarmazynHandshake)
  gossip        → propagacja stanu przez pierścień węzłów

Topologia (konfigurowana):
  mesh    → każdy z każdym (małe klastry, ≤8 węzłów)
  ring    → każdy z K sąsiadami (skalowalne, domyślne)
  star    → węzeł koordynator + workery (max wydajność)

Integracja z shell.py:
  reg("CLUSTER", cmd_cluster_wrap, ..., category="cluster")

Komendy ksh:
  CLUSTER STATUS             — stan klastra
  CLUSTER JOIN <host> [port] — dołącz do klastra
  CLUSTER SUBMIT <atom_id>   — wyślij atom do wykonania
  CLUSTER STEAL              — pobierz gorący atom z innego węzła
  CLUSTER NODES              — lista węzłów
  CLUSTER HEATMAP            — mapa temperatury klastra

Użycie standalone:
  python3 karmazyn_cluster.py --demo
  python3 karmazyn_cluster.py --node --port 7800
"""

import hashlib
import json
import os
import secrets
import socket
import struct
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


# ── Importy KarmazynOS ────────────────────────────────────────────────────────

try:
    from karmazyn_phi import PhiSpace
    _PHI_AVAILABLE = True
except ImportError:
    _PHI_AVAILABLE = False

try:
    from karmazyn_handshake import KarmazynHandshake, _node_id, _serialize_atoms
    _HANDSHAKE_AVAILABLE = True
except ImportError:
    _HANDSHAKE_AVAILABLE = False
    def _node_id() -> str:
        return "node_" + hashlib.sha256(
            socket.gethostname().encode()).hexdigest()[:12]
    def _serialize_atoms(phi) -> list:
        try:
            return [{"id": a.id, "T": float(a.T), "S": str(a.S),
                     "E": str(a.E), "state": str(a.state), "age": int(a.age)}
                    for a in phi.matrix.atoms()
                    if float(getattr(a,"T",0)) > 2.0 and str(getattr(a,"state","")) != "TOMB"]
        except Exception:
            return []

try:
    from karmazyn_syslog import SystemLog
    REGISTRY = SystemLog()
except ImportError:
    class _MinLog:
        def register(self, *a, **kw): pass
        def log(self, level, msg, service="cluster", **kw):
            if level not in ("DEBUG",): print(f"[{level}] {service}: {msg}")
    REGISTRY = _MinLog()


# ── Stałe ─────────────────────────────────────────────────────────────────────

CLUSTER_VERSION    = "KCL-1.0"
GOSSIP_PORT_OFFSET = 100          # port gossip = handshake_port + 100
GOSSIP_INTERVAL    = 2.0          # s — co ile sekund gossip tick
NODE_TIMEOUT_SEC   = 30.0         # s — węzeł offline po braku heartbeat
STEAL_THRESHOLD    = 70.0         # T — atomy gorętsze migrują przy work steal
STEAL_COOL_DOWN    = 10.0         # T — docelowa T atomu po kradzieży (nie przepalamy)
RING_K             = 2            # liczba sąsiadów w topologii ring
FRAME_MAX          = 4 * 1024 * 1024  # 4 MB


# ─────────────────────────────────────────────────────────────────────────────
# Transport (współdzielony z handshake, minimalna kopia)
# ─────────────────────────────────────────────────────────────────────────────

def _send_frame(sock: socket.socket, data: bytes) -> None:
    if len(data) > FRAME_MAX:
        raise ValueError(f"Frame za duży: {len(data)}")
    sock.sendall(struct.pack(">I", len(data)) + data)

def _recv_frame(sock: socket.socket, timeout: float = 5.0) -> bytes:
    sock.settimeout(timeout)
    hdr = b""
    while len(hdr) < 4:
        c = sock.recv(4 - len(hdr))
        if not c: raise ConnectionError("closed")
        hdr += c
    n = struct.unpack(">I", hdr)[0]
    if n > FRAME_MAX: raise ValueError(f"Frame za duży: {n}")
    buf = b""
    while len(buf) < n:
        c = sock.recv(n - len(buf))
        if not c: raise ConnectionError("closed")
        buf += c
    return buf

def _sjson(sock, obj): _send_frame(sock, json.dumps(obj, sort_keys=True).encode())
def _rjson(sock, t=5.0): return json.loads(_recv_frame(sock, t).decode("utf-8", errors="replace"))


# ─────────────────────────────────────────────────────────────────────────────
# NodeInfo — opis węzła w klastrze
# ─────────────────────────────────────────────────────────────────────────────

class NodeInfo:
    """Opis węzła klastra — przechowywany lokalnie przez każdy węzeł."""

    __slots__ = ("node_id", "host", "port", "last_seen",
                 "hot_count", "warm_count", "cold_count",
                 "load", "version", "alive")

    def __init__(self, node_id: str, host: str, port: int):
        self.node_id   = node_id
        self.host      = host
        self.port      = port
        self.last_seen = time.monotonic()
        self.hot_count = 0
        self.warm_count= 0
        self.cold_count= 0
        self.load      = 0.0      # 0.0 = idle, 1.0 = full
        self.version   = CLUSTER_VERSION
        self.alive     = True

    def update_heartbeat(self, data: dict) -> None:
        self.last_seen  = time.monotonic()
        self.hot_count  = data.get("hot",  0)
        self.warm_count = data.get("warm", 0)
        self.cold_count = data.get("cold", 0)
        self.load       = data.get("load", 0.0)
        self.alive      = True

    @property
    def is_stale(self) -> bool:
        return (time.monotonic() - self.last_seen) > NODE_TIMEOUT_SEC

    def to_dict(self) -> dict:
        return {
            "node_id":    self.node_id,
            "host":       self.host,
            "port":       self.port,
            "hot":        self.hot_count,
            "warm":       self.warm_count,
            "cold":       self.cold_count,
            "load":       round(self.load, 3),
            "last_seen":  round(time.monotonic() - self.last_seen, 1),
            "alive":      self.alive and not self.is_stale,
        }


# ─────────────────────────────────────────────────────────────────────────────
# PhiShard — lokalna partycja phi-space węzła
# ─────────────────────────────────────────────────────────────────────────────

class PhiShard:
    """
    Lokalna partycja phi-space z metadanymi klastra.

    Każdy węzeł ma własny PhiShard. Shard wie o swojej "temperaturze"
    (średnie T atomów) i może obliczyć load względem innych węzłów.
    """

    def __init__(self, phi: Any, node_id: str):
        self.phi     = phi
        self.node_id = node_id
        self._lock   = threading.Lock()

    def stats(self) -> dict:
        """Termodynamiczny status shardu."""
        try:
            atoms = self.phi.matrix.atoms()
        except Exception:
            return {"hot": 0, "warm": 0, "cold": 0, "total": 0, "load": 0.0}
        hot  = sum(1 for a in atoms if float(getattr(a,"T",0)) > 70)
        warm = sum(1 for a in atoms if 30 < float(getattr(a,"T",0)) <= 70)
        cold = sum(1 for a in atoms if 2  < float(getattr(a,"T",0)) <= 30)
        tot  = len(atoms)
        # Load = proporcja gorących atomów (gorące = obciążenie obliczeniowe)
        load = hot / max(1, tot)
        return {"hot": hot, "warm": warm, "cold": cold,
                "total": tot, "load": round(load, 3)}

    def hot_atoms(self, threshold: float = STEAL_THRESHOLD) -> List[dict]:
        """Atomy gotowe do work steal (T > threshold)."""
        try:
            return [
                {"id": a.id, "T": float(a.T), "S": str(a.S),
                 "E": str(a.E), "state": str(a.state)}
                for a in self.phi.matrix.atoms()
                if float(getattr(a,"T",0)) > threshold
                and str(getattr(a,"state","")) not in ("TOMB",)
            ]
        except Exception:
            return []

    def steal_atom(self, atom_id: str,
                   cool_to: float = STEAL_COOL_DOWN) -> Optional[dict]:
        """
        Work steal: zwróć atom i ostudź go lokalnie.
        Ostudzone = nie będzie wysyłane ponownie przy następnym steal.
        """
        with self._lock:
            try:
                atom = self.phi.get_atom(atom_id)
                if atom is None:
                    return None
                rec = {
                    "id":    atom.id,
                    "T":     float(atom.T),
                    "S":     str(atom.S),
                    "E":     str(atom.E),
                    "state": str(atom.state),
                    "age":   int(getattr(atom,"age",0)),
                    "T_max": float(getattr(atom,"T_max",100.0)),
                    "_stolen_from": self.node_id,
                }
                # Ostudź lokalnie — atom pozostaje ale nie jest już "gorący"
                atom.T = cool_to
                try: atom.touch()
                except Exception: pass
                return rec
            except Exception:
                return None

    def inject_atom(self, rec: dict) -> bool:
        """Wstrzyknij ukradziony atom do lokalnego phi-space."""
        with self._lock:
            try:
                existing = self.phi.get_atom(rec["id"])
                if existing is not None:
                    # Atom już istnieje — weź wyższe T (nie traćmy pracy)
                    if float(rec.get("T", 0)) > float(getattr(existing,"T",0)):
                        existing.T = float(rec["T"])
                        try: existing.touch()
                        except Exception: pass
                    return True
                # Nowy atom
                na = self.phi.create_atom(
                    rec["id"], S=rec.get("S",""), E=rec.get("E",""), T=float(rec.get("T",50)))
                if na:
                    try:
                        na.state = rec.get("state","WARM")
                        na.age   = rec.get("age", 0)
                        na.T_max = rec.get("T_max", 100.0)
                        na.touch()
                    except Exception: pass
                return True
            except Exception:
                return False


# ─────────────────────────────────────────────────────────────────────────────
# GossipProtocol — propagacja stanu przez pierścień
# ─────────────────────────────────────────────────────────────────────────────

class GossipProtocol:
    """
    Gossip przez TCP ring — każdy węzeł rozmawia z K sąsiadami.

    Wiadomości:
      HEARTBEAT  → aktualizacja stats węzła
      JOIN       → nowy węzeł wchodzi do klastra
      LEAVE      → węzeł opuszcza klaster
      STEAL_REQ  → prośba o gorący atom
      STEAL_ACK  → odpowiedź z atomem
      BROADCAST  → propagacja zdarzenia przez cały klaster

    Gossip jest eventually consistent — nie wymaga quorum.
    """

    def __init__(self, cluster: "KarmazynCluster"):
        self.cluster  = cluster
        self._running = False
        self._server  = None
        self._thread  = None

    def start(self, port: int) -> None:
        self._running = True
        self._server  = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("0.0.0.0", port))
        self._server.listen(16)
        self._server.settimeout(1.0)
        self._thread = threading.Thread(
            target=self._serve_loop, daemon=True, name="gossip-server")
        self._thread.start()
        # Gossip tick w osobnym wątku
        threading.Thread(
            target=self._tick_loop, daemon=True, name="gossip-tick").start()
        REGISTRY.log("INFO", f"Gossip server na porcie {port}", service="cluster")

    def stop(self) -> None:
        self._running = False
        if self._server:
            try: self._server.close()
            except Exception: pass

    def _serve_loop(self) -> None:
        while self._running:
            try:
                conn, addr = self._server.accept()
                threading.Thread(
                    target=self._handle,
                    args=(conn,),
                    daemon=True).start()
            except socket.timeout:
                continue
            except Exception:
                break

    def _handle(self, conn: socket.socket) -> None:
        try:
            msg = _rjson(conn)
            kind = msg.get("kind", "")

            if kind == "HEARTBEAT":
                self.cluster._on_heartbeat(msg)
                _sjson(conn, {"ok": True})

            elif kind == "JOIN":
                self.cluster._on_join(msg)
                # Odpowiedz z listą znanych węzłów
                _sjson(conn, {
                    "ok":    True,
                    "nodes": [n.to_dict() for n in self.cluster.nodes.values()],
                })

            elif kind == "STEAL_REQ":
                atom_id = msg.get("atom_id")
                rec     = self.cluster.shard.steal_atom(atom_id)
                _sjson(conn, {"ok": rec is not None, "atom": rec})

            elif kind == "BROADCAST":
                self.cluster._on_broadcast(msg)
                _sjson(conn, {"ok": True})

            elif kind == "HEATMAP_REQ":
                stats = self.cluster.shard.stats()
                _sjson(conn, {
                    "ok":      True,
                    "node_id": self.cluster.local_id,
                    "stats":   stats,
                    "atoms":   self.cluster.shard.hot_atoms(40.0),
                })

        except Exception as e:
            try: _sjson(conn, {"ok": False, "error": str(e)})
            except Exception: pass
        finally:
            try: conn.close()
            except Exception: pass

    def _tick_loop(self) -> None:
        """Regularny gossip tick — rozsyłaj heartbeat do sąsiadów."""
        while self._running:
            time.sleep(GOSSIP_INTERVAL)
            try:
                self._send_heartbeat()
                self._prune_stale_nodes()
            except Exception:
                pass

    def _send_heartbeat(self) -> None:
        stats   = self.cluster.shard.stats()
        payload = {
            "kind":    "HEARTBEAT",
            "node_id": self.cluster.local_id,
            "host":    self.cluster.host,
            "port":    self.cluster.port,
            "ts":      time.time(),
            **stats,
        }
        # [FIX 4] Aktualizuj własny NodeInfo — status() zobaczy aktualne load
        local_node = self.cluster.nodes.get(self.cluster.local_id)
        if local_node:
            local_node.update_heartbeat(payload)
        for peer in self._select_peers():
            self._gossip_send(peer, payload)

    def _select_peers(self) -> List[NodeInfo]:
        """Topologia ring — wybierz K sąsiadów."""
        nodes = [n for n in self.cluster.nodes.values()
                 if n.node_id != self.cluster.local_id and not n.is_stale]
        if not nodes:
            return []
        # Deterministyczny ring — posortuj po node_id
        nodes.sort(key=lambda n: n.node_id)
        return nodes[:RING_K]

    def _gossip_send(self, peer: NodeInfo, payload: dict) -> Optional[dict]:
        """Wyślij wiadomość gossip do jednego węzła."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3.0)
            sock.connect((peer.host, peer.port + GOSSIP_PORT_OFFSET))
            _sjson(sock, payload)
            resp = _rjson(sock, 3.0)
            sock.close()
            return resp
        except Exception:
            peer.alive = False
            return None

    def send_to(self, peer: NodeInfo, payload: dict) -> Optional[dict]:
        return self._gossip_send(peer, payload)

    def broadcast(self, payload: dict) -> int:
        """Wyślij do wszystkich aktywnych węzłów. Zwraca liczbę sukcesów."""
        payload["kind"] = "BROADCAST"
        payload.setdefault("origin", self.cluster.local_id)
        count = 0
        for peer in self.cluster.nodes.values():
            if peer.node_id != self.cluster.local_id and not peer.is_stale:
                if self._gossip_send(peer, payload):
                    count += 1
        return count

    def _prune_stale_nodes(self) -> None:
        stale = [nid for nid, n in self.cluster.nodes.items() if n.is_stale]
        for nid in stale:
            self.cluster.nodes[nid].alive = False
            REGISTRY.log("WARN", f"Węzeł offline: {nid}", service="cluster")


# ─────────────────────────────────────────────────────────────────────────────
# ThermalLoadBalancer — work stealing oparte o temperaturę
# ─────────────────────────────────────────────────────────────────────────────

class ThermalLoadBalancer:
    """
    Balansowanie obciążenia przez termodynamikę.

    Zasada:
      Gorące atomy (T > STEAL_THRESHOLD) na przeciążonym węźle
      są migrowane do zimnych (niskie load) węzłów.

    To nie jest klasyczny load balancer — to dyfuzja termiczna.
    Atomy płyną od gorących węzłów do zimnych tak jak ciepło
    płynie od gorących ciał do zimnych.
    """

    def __init__(self, cluster: "KarmazynCluster"):
        self.cluster = cluster

    def balance(self) -> dict:
        """
        Jeden krok balansowania.
        Zwraca statystyki migracji.
        """
        local_stats = self.cluster.shard.stats()
        local_load  = local_stats["load"]

        results = {"migrated": 0, "rejected": 0, "peers_checked": 0}

        # Steal gdy mamy mniej niż 60% load (jest miejsce na nowe atomy)
        if local_load > 0.6:
            return results  # sami jesteśmy zajęci

        # Znajdź przeciążone węzły
        # [FIX 3] Nie polegaj na load z heartbeat (może nie być aktualny).
        # Odpytaj każdego peera przez HEATMAP_REQ — niech sam powie czy ma gorące atomy.
        all_peers = [
            n for n in self.cluster.nodes.values()
            if n.node_id != self.cluster.local_id
            and not n.is_stale
        ]

        for peer in all_peers[:4]:   # max 4 węzły na raz
            results["peers_checked"] += 1
            stolen = self._steal_from(peer)
            results["migrated"] += stolen

        return results

    def _steal_from(self, peer: NodeInfo) -> int:
        """
        Pobierz gorące atomy od przeciążonego węzła.
        Zwraca liczbę pomyślnie skradzionych atomów.
        """
        # Najpierw zapytaj o listę gorących atomów przez heatmap
        try:
            resp = self.cluster.gossip.send_to(peer, {
                "kind": "HEATMAP_REQ",
            })
            if not resp or not resp.get("ok"):
                return 0

            hot_atoms = resp.get("atoms", [])
            stolen    = 0

            for atom_rec in hot_atoms[:5]:   # max 5 atomów na raz
                atom_id = atom_rec.get("id", "")
                if not atom_id:
                    continue

                # Poproś o kradzież
                steal_resp = self.cluster.gossip.send_to(peer, {
                    "kind":    "STEAL_REQ",
                    "atom_id": atom_id,
                })
                if steal_resp and steal_resp.get("ok") and steal_resp.get("atom"):
                    rec = steal_resp["atom"]
                    if self.cluster.shard.inject_atom(rec):
                        stolen += 1
                        REGISTRY.log(
                            "INFO",
                            f"Steal: {atom_id} T={rec.get('T',0):.1f} "
                            f"od {peer.node_id[:8]}",
                            service="cluster")

            return stolen

        except Exception:
            return 0


# ─────────────────────────────────────────────────────────────────────────────
# KarmazynCluster — główny koordynator klastra
# ─────────────────────────────────────────────────────────────────────────────

class KarmazynCluster:
    """
    HyperCluster KarmazynOS — N węzłów jako superkomputer termodynamiczny.

    Każdy węzeł jest równorzędny (P2P, bez mastera).
    Koordynacja przez gossip + termodynamikę phi-space.

    Użycie:
        cluster = KarmazynCluster(phi_space, host="0.0.0.0", port=7800)
        cluster.start()

        # Dołącz do istniejącego klastra
        cluster.join("192.168.1.42", 7800)

        # Sprawdź stan
        print(cluster.status())
    """

    def __init__(self,
                 phi:     Any,
                 host:    str = "0.0.0.0",
                 port:    int = 7800,
                 log_fn:  Optional[Callable] = None,
                 psk:     Optional[bytes] = None,
                 node_id: Optional[str] = None):
        self.phi      = phi
        self.host     = host
        self.port     = port
        self._log     = log_fn or print
        self._psk     = psk
        self.local_id = node_id or (_node_id() + f"_{port}")

        # Komponenty
        self.shard    = PhiShard(phi, self.local_id)
        self.gossip   = GossipProtocol(self)
        self.balancer = ThermalLoadBalancer(self)

        # Rejestr węzłów
        self.nodes:  Dict[str, NodeInfo] = {}
        self._lock   = threading.Lock()

        # Siebie też dodaj do rejestru
        me = NodeInfo(self.local_id, host, port)
        self.nodes[self.local_id] = me

        # Wątek balansowania
        self._balance_thread: Optional[threading.Thread] = None
        self._running = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> "KarmazynCluster":
        """Uruchom węzeł klastra (gossip + balancer)."""
        self._running = True
        gossip_port   = self.port + GOSSIP_PORT_OFFSET
        self.gossip.start(gossip_port)

        # Opcjonalnie: serwer handshake dla phi-sync przy JOIN
        if _HANDSHAKE_AVAILABLE:
            def _hs_serve_forever():
                while self._running:
                    try:
                        hs = KarmazynHandshake(self.phi, log_fn=self._log,
                                               psk=self._psk)
                        hs.serve(host=self.host, port=self.port,
                                 timeout=NODE_TIMEOUT_SEC)
                    except Exception:
                        time.sleep(1)
            threading.Thread(
                target=_hs_serve_forever, daemon=True,
                name="hs-server").start()

        # Wątek balansowania obciążenia
        self._balance_thread = threading.Thread(
            target=self._balance_loop,
            daemon=True,
            name="thermal-balancer")
        self._balance_thread.start()

        self._log(f"[KCL] Węzeł {self.local_id} uruchomiony")
        self._log(f"[KCL] Gossip port: {gossip_port}")
        REGISTRY.log("INFO", f"Klaster start: {self.local_id}", service="cluster")
        return self

    def stop(self) -> None:
        self._running = False
        self.gossip.stop()
        REGISTRY.log("INFO", f"Klaster stop: {self.local_id}", service="cluster")

    def join(self, peer_host: str, peer_port: int = 7800, phi_sync: bool = True) -> bool:
        """
        Dołącz do istniejącego klastra przez znany węzeł.

        1. Wyślij JOIN do peer → dostań listę węzłów
        2. Wykonaj handshake phi-space z peer (sync atomów)
        3. Roześlij własny JOIN do poznanych węzłów
        """
        self._log(f"[KCL] Dołączam do klastra przez {peer_host}:{peer_port}")

        # Krok 1: JOIN gossip
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10.0)
            sock.connect((peer_host, peer_port + GOSSIP_PORT_OFFSET))
            _sjson(sock, {
                "kind":    "JOIN",
                "node_id": self.local_id,
                "host":    self.host,
                "port":    self.port,
                "ts":      time.time(),
                **self.shard.stats(),
            })
            resp = _rjson(sock, 10.0)
            sock.close()

            if not resp.get("ok"):
                self._log(f"[KCL] JOIN odrzucony: {resp.get('error','?')}")
                return False

            # Zarejestruj poznane węzły
            for node_data in resp.get("nodes", []):
                nid = node_data.get("node_id","")
                if nid and nid != self.local_id:
                    with self._lock:
                        if nid not in self.nodes:
                            n = NodeInfo(nid, node_data["host"], node_data["port"])
                            n.update_heartbeat(node_data)
                            self.nodes[nid] = n
            self._log(f"[KCL] Poznano {len(resp.get('nodes',[]))} węzłów")

        except Exception as e:
            self._log(f"[KCL] JOIN gossip błąd: {e}")
            return False

        # Krok 2: Handshake phi-space (sync atomów z peer)
        # [FIX 5] phi-sync jest opcjonalny — wymaga uruchomionego serwera handshake
        # na porcie peer_port. Bez tego JOIN działa, tylko bez wstępnej replikacji atomów.
        if phi_sync and _HANDSHAKE_AVAILABLE and peer_port != self.port:
            try:
                hs = KarmazynHandshake(self.phi, log_fn=self._log, psk=self._psk)
                result = hs.connect(peer_host, port=peer_port)
                self._log(
                    f"[KCL] Phi-sync: +{result.get('added',0)} atomów, "
                    f"hash={result.get('state_hash','?')[:8]}")
            except Exception as e:
                self._log(f"[KCL] Phi-sync skip: {e}")

        REGISTRY.log("INFO",
                     f"Dołączono do klastra ({len(self.nodes)} węzłów)",
                     service="cluster")
        return True

    # ── Operacje na atomach ───────────────────────────────────────────────────

    def submit(self, atom_id: str,
               S: str = "task", E: str = "",
               T: float = 80.0,
               broadcast: bool = True) -> bool:
        """
        Wyślij zadanie do klastra.
        Tworzy atom o wysokiej T — thermal engine zadba o routing.
        Jeśli broadcast=True, propaguje do wszystkich węzłów.
        """
        try:
            # Stwórz lokalnie
            a = self.phi.create_atom(atom_id, S=S, E=E, T=T)
            if a:
                try: a.touch()
                except Exception: pass
        except Exception as e:
            self._log(f"[KCL] Submit błąd lokalny: {e}")
            return False

        if broadcast:
            n = self.gossip.broadcast({
                "type":    "SUBMIT",
                "atom_id": atom_id,
                "S": S, "E": E, "T": T,
            })
            self._log(f"[KCL] Submit {atom_id} → {n} węzłów")

        return True

    def steal(self) -> int:
        """Uruchom work stealing — pobierz gorące atomy od przeciążonych węzłów."""
        result = self.balancer.balance()
        return result["migrated"]

    # ── Monitoring ────────────────────────────────────────────────────────────

    def status(self) -> dict:
        """Pełny status klastra."""
        alive  = [n for n in self.nodes.values() if not n.is_stale]
        stale  = [n for n in self.nodes.values() if n.is_stale]
        # Lokalne stats bezpośrednio z shard — nie czekaj na heartbeat
        local  = self.shard.stats()
        # cluster_* = lokalne (bezpośrednie) + zdalne (gossip, mogą być stale)
        remote = [n for n in alive if n.node_id != self.local_id]
        return {
            "local_node":    self.local_id,
            "total_nodes":   len(self.nodes),
            "alive_nodes":   len(alive),
            "stale_nodes":   len(stale),
            "local_stats":   local,
            "cluster_hot":   local["hot"]  + sum(n.hot_count  for n in remote),
            "cluster_warm":  local["warm"] + sum(n.warm_count for n in remote),
            "cluster_cold":  local["cold"] + sum(n.cold_count for n in remote),
            "avg_load":      round(
                (local["load"] + sum(n.load for n in remote))
                / max(1, len(alive)), 3),
        }

    def heatmap(self) -> List[dict]:
        """
        Mapa temperatury całego klastra — jeden wiersz per węzeł.
        Lokalny węzeł — dane bezpośrednie.
        Zdalne węzły — ostatnie dane z gossip heartbeat.
        """
        result = []

        # Lokalny
        local_stats = self.shard.stats()
        result.append({
            "node_id": self.local_id[:12],
            "host":    self.host,
            "port":    self.port,
            **local_stats,
            "local":   True,
        })

        # Zdalne
        for n in self.nodes.values():
            if n.node_id == self.local_id: continue
            result.append({
                "node_id":  n.node_id[:12],
                "host":     n.host,
                "port":     n.port,
                "hot":      n.hot_count,
                "warm":     n.warm_count,
                "cold":     n.cold_count,
                "load":     n.load,
                "alive":    not n.is_stale,
                "local":    False,
            })

        result.sort(key=lambda x: -x.get("hot", 0))
        return result

    def resonance_zone(self, threshold: float = 40.0) -> dict:
        """
        Wspólna strefa klastra — atomy gorące na WIELU węzłach jednocześnie.
        Im więcej węzłów ma gorący ten sam atom, tym mocniejszy rezonans.
        """
        # Lokalnie możemy tylko sprawdzić własne gorące atomy
        # i porównać z tym co wiemy o innych węzłach przez gossip
        local_hot = {a["id"]: a["T"]
                     for a in self.shard.hot_atoms(threshold)}
        alive_count = sum(1 for n in self.nodes.values() if not n.is_stale)

        return {
            "local_hot_count": len(local_hot),
            "alive_nodes":     alive_count,
            "note": (
                "Pełny rezonans wymaga karmazyn_gossip.py z atom-level propagation. "
                "Aktualnie: lokalny widok. "
                f"Gorące lokalnie: {list(local_hot.keys())[:5]}"
            ),
        }

    # ── Callbacks gossip ──────────────────────────────────────────────────────

    def _on_heartbeat(self, msg: dict) -> None:
        nid = msg.get("node_id","")
        if not nid or nid == self.local_id: return
        with self._lock:
            if nid not in self.nodes:
                self.nodes[nid] = NodeInfo(
                    nid, msg.get("host","?"), msg.get("port",7800))
            self.nodes[nid].update_heartbeat(msg)

    def _on_join(self, msg: dict) -> None:
        nid = msg.get("node_id","")
        if not nid or nid == self.local_id: return  # [FIX 2] OK — tylko w JOIN
        with self._lock:
            n = NodeInfo(nid, msg.get("host","?"), msg.get("port",7800))
            n.update_heartbeat(msg)
            self.nodes[nid] = n
        self._log(f"[KCL] Nowy węzeł: {nid[:12]} @ {msg.get('host','?')}")
        REGISTRY.log("INFO", f"JOIN: {nid[:12]}", service="cluster")

    def _on_broadcast(self, msg: dict) -> None:
        kind = msg.get("type","")
        if kind == "SUBMIT":
            # Inny węzeł wysłał zadanie — dodaj lokalnie jeśli nie mamy
            atom_id = msg.get("atom_id","")
            if atom_id:
                existing = None
                try: existing = self.phi.get_atom(atom_id)
                except Exception: pass
                if existing is None:
                    try:
                        na = self.phi.create_atom(
                            atom_id,
                            S=msg.get("S","task"),
                            E=msg.get("E",""),
                            T=float(msg.get("T",50.0)))
                        if na:
                            try: na.touch()
                            except Exception: pass
                    except Exception: pass

    # ── Balance loop ──────────────────────────────────────────────────────────

    def _balance_loop(self) -> None:
        """Periodyczny work stealing — co 2× GOSSIP_INTERVAL."""
        while self._running:
            time.sleep(GOSSIP_INTERVAL * 2)
            try:
                r = self.balancer.balance()
                if r["migrated"] > 0:
                    self._log(
                        f"[KCL] Balancer: +{r['migrated']} atomów skradzionych "
                        f"od {r['peers_checked']} węzłów")
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Komenda shella
# ─────────────────────────────────────────────────────────────────────────────

# Globalny singleton klastra — inicjalizowany przy pierwszym CLUSTER JOIN/START
_CLUSTER_INSTANCE: Optional[KarmazynCluster] = None


def cmd_cluster(args, runtime=None, term_state=None, **_kw) -> str:
    """
    CLUSTER STATUS            — stan klastra
    CLUSTER START [port]      — uruchom węzeł
    CLUSTER JOIN <host> [port]— dołącz do klastra
    CLUSTER NODES             — lista węzłów
    CLUSTER HEATMAP           — mapa temperatury
    CLUSTER SUBMIT <id> [T]   — wyślij zadanie
    CLUSTER STEAL             — work stealing
    CLUSTER STOP              — zatrzymaj węzeł
    """
    global _CLUSTER_INSTANCE

    def out(msg: str) -> None:
        if term_state: term_state.append(msg, (180, 220, 100))
        else: print(msg)

    if runtime is None:
        return "Brak runtime."

    if not args:
        return ("CLUSTER STATUS | START [port] | JOIN <host> [port] | "
                "NODES | HEATMAP | SUBMIT <id> [T] | STEAL | STOP")

    sub = args[0].upper()

    if sub == "START":
        if _CLUSTER_INSTANCE:
            return "Klaster już uruchomiony."
        port = int(args[1]) if len(args) > 1 and args[1].isdigit() else 7800
        psk  = os.environ.get("KARM_PSK", "").encode() or None
        _CLUSTER_INSTANCE = KarmazynCluster(
            runtime, port=port, log_fn=out, psk=psk).start()
        return f"Klaster uruchomiony: {_CLUSTER_INSTANCE.local_id} port={port}"

    if sub == "JOIN":
        if not _CLUSTER_INSTANCE:
            port = 7800
            psk  = os.environ.get("KARM_PSK", "").encode() or None
            _CLUSTER_INSTANCE = KarmazynCluster(
                runtime, port=port, log_fn=out, psk=psk).start()
        if len(args) < 2:
            return "CLUSTER JOIN <host> [port]"
        host  = args[1]
        port  = int(args[2]) if len(args) > 2 and args[2].isdigit() else 7800
        ok    = _CLUSTER_INSTANCE.join(host, port)
        return f"{'Dołączono do' if ok else 'Błąd dołączania do'} {host}:{port}"

    if not _CLUSTER_INSTANCE:
        return "Klaster nie uruchomiony. Wpisz: CLUSTER START"

    if sub == "STATUS":
        s = _CLUSTER_INSTANCE.status()
        lines = [
            "──────────────────────────────────",
            f"  Węzeł:      {s['local_node']}",
            f"  W klastrze: {s['alive_nodes']}/{s['total_nodes']} węzłów",
            f"  Lokalnie:   HOT={s['local_stats']['hot']} "
            f"WARM={s['local_stats']['warm']} "
            f"COLD={s['local_stats']['cold']}",
            f"  Klaster:    HOT={s['cluster_hot']} WARM={s['cluster_warm']}",
            f"  Avg load:   {s['avg_load']:.1%}",
            "──────────────────────────────────",
        ]
        return "\n".join(lines)

    if sub == "NODES":
        rows = [f"  {'node_id':16} {'host':20} {'port':6} {'load':6} {'hot':4} status"]
        rows.append("  " + "─"*62)
        for n in _CLUSTER_INSTANCE.nodes.values():
            d = n.to_dict()
            status = "OK" if d["alive"] else "OFFLINE"
            rows.append(
                f"  {d['node_id'][:16]:16} {d['host']:20} {d['port']:6} "
                f"{d['load']:5.1%} {d['hot']:4} {status}")
        return "\n".join(rows)

    if sub == "HEATMAP":
        hm   = _CLUSTER_INSTANCE.heatmap()
        rows = [f"  {'node':12} {'host':16} {'HOT':>4} {'WARM':>4} {'COLD':>4} {'load':>6}"]
        rows.append("  " + "─"*52)
        for r in hm:
            marker = " ← lokalny" if r["local"] else ""
            rows.append(
                f"  {r['node_id']:12} {r['host']:16} "
                f"{r.get('hot',0):4} {r.get('warm',0):4} {r.get('cold',0):4} "
                f"{r.get('load',0):5.1%}{marker}")
        return "\n".join(rows)

    if sub == "SUBMIT":
        if len(args) < 2: return "CLUSTER SUBMIT <id> [T]"
        atom_id = args[1]
        T       = float(args[2]) if len(args) > 2 else 80.0
        ok      = _CLUSTER_INSTANCE.submit(atom_id, T=T)
        return f"{'OK' if ok else 'BŁĄD'}: submit {atom_id} T={T}"

    if sub == "STEAL":
        n = _CLUSTER_INSTANCE.steal()
        return f"Work steal: +{n} atomów"

    if sub == "STOP":
        _CLUSTER_INSTANCE.stop()
        _CLUSTER_INSTANCE = None
        return "Klaster zatrzymany."

    return f"Nieznana subkomenda: {sub}"


# ─────────────────────────────────────────────────────────────────────────────
# Demo
# ─────────────────────────────────────────────────────────────────────────────

def _run_demo() -> None:
    print("=" * 64)
    print("  KarmazynOS HyperCluster — DEMO (3 węzły, loopback)")
    print("=" * 64)

    # Mock PhiSpace
    class _MockAtom:
        def __init__(self, id, S="", E="", T=50.0):
            self.id    = id; self.S = S; self.E = E; self.T = T
            self.T_max = 100.0; self.state = "WARM"; self.age = 0
        def touch(self): self.T = min(self.T_max, self.T + 2)

    class _MockPhi:
        def __init__(self, atoms):
            self._a = list(atoms)
            self._d = {a.id: a for a in self._a}
            self.matrix = type("M", (), {"atoms": lambda s: self._a})()
        def get_atom(self, id): return self._d.get(id)
        def create_atom(self, id, S="", E="", T=50.0):
            a = _MockAtom(id, S, E, T)
            self._a.append(a); self._d[id] = a; return a

    phi_a = _MockPhi([_MockAtom("sys.init", T=90), _MockAtom("task.alpha", T=75)])
    phi_b = _MockPhi([_MockAtom("sys.init", T=60), _MockAtom("task.beta",  T=80)])
    phi_c = _MockPhi([_MockAtom("sys.init", T=40), _MockAtom("task.gamma", T=30)])

    logs = {"A": [], "B": [], "C": []}

    psk = b"demo_karmazyn_cluster"

    c_a = KarmazynCluster(phi_a, host="127.0.0.1", port=17800,
                           log_fn=lambda m: logs["A"].append(m), psk=psk,
                           node_id="node_demo_A")
    c_b = KarmazynCluster(phi_b, host="127.0.0.1", port=17801,
                           log_fn=lambda m: logs["B"].append(m), psk=psk,
                           node_id="node_demo_B")
    c_c = KarmazynCluster(phi_c, host="127.0.0.1", port=17802,
                           log_fn=lambda m: logs["C"].append(m), psk=psk,
                           node_id="node_demo_C")

    c_a.start()
    c_b.start()
    c_c.start()
    time.sleep(0.5)  # daj czas na bind portów

    print("\n[1] B dołącza do A...")
    c_b.join("127.0.0.1", 17800)
    time.sleep(0.3)

    print("[2] C dołącza do A (bez phi-sync — testujemy steal)...")
    c_c.join("127.0.0.1", 17800, phi_sync=False)
    time.sleep(0.3)

    print("[3] C kradnie gorące atomy od A i B (work stealing)...")
    sc = c_c.shard.stats()
    print(f"    C load przed: HOT={sc['hot']} WARM={sc['warm']} load={sc['load']:.0%}")
    print(f"    C atomy przed: {[a.id for a in phi_c._a]}")
    stolen = c_c.steal()
    sc2 = c_c.shard.stats()
    print(f"    Skradzione: {stolen} atomów")
    print(f"    C load po:    HOT={sc2['hot']} WARM={sc2['warm']} load={sc2['load']:.0%}")
    print(f"    C atomy po:   {[a.id for a in phi_c._a]}")

    print("\n[4] A wysyła zadanie do klastra (broadcast)...")
    c_a.submit("job.karmazyn_sync", S="cluster_job",
                E="sync phi-space across all nodes", T=85.0)
    time.sleep(0.8)

    print("\n[5] Heatmap klastra (po broadcast):")
    for node, c in [("A", c_a), ("B", c_b), ("C", c_c)]:
        s = c.shard.stats()
        print(f"  Węzeł {node}: HOT={s['hot']} WARM={s['warm']} "
              f"COLD={s['cold']} load={s['load']:.1%}")

    print("\n[6] Atomy phi C (po steal + broadcast):")
    print(f"  {[a.id for a in phi_c._a]}")

    print("\n[7] Status klastra z perspektywy A:")
    st = c_a.status()
    print(f"  Węzłów alive:  {st['alive_nodes']}/{st['total_nodes']}")
    print(f"  Cluster HOT:   {st['cluster_hot']}")

    c_a.stop(); c_b.stop(); c_c.stop()
    print("\n" + "=" * 64)


# ─────────────────────────────────────────────────────────────────────────────
# Rejestracja w shell.py — dodaj do bloku programów systemowych:
# ─────────────────────────────────────────────────────────────────────────────
# try:
#     from karmazyn_cluster import cmd_cluster as _cmd_cluster
#     def cmd_cluster_wrap(args):
#         term = (DISPLAY.renderer.term_state
#                 if DISPLAY and DISPLAY.available and DISPLAY.renderer else None)
#         return _cmd_cluster(args, runtime=RUNTIME, term_state=term)
#     reg("CLUSTER", cmd_cluster_wrap,
#         "HyperKlaster KarmazynOS [STATUS|START|JOIN|NODES|HEATMAP|SUBMIT|STEAL]",
#         category="cluster")
# except ImportError as e:
#     REGISTRY.register("cluster", ServiceStatus.MISSING, message=str(e)[:60])
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="KarmazynOS HyperCluster v1.0")
    ap.add_argument("--demo",  action="store_true")
    ap.add_argument("--node",  action="store_true", help="Uruchom węzeł")
    ap.add_argument("--join",  metavar="HOST",       help="Dołącz do klastra")
    ap.add_argument("--port",  type=int, default=7800)
    opt = ap.parse_args()

    if opt.demo:
        _run_demo()
    elif opt.node:
        if not _PHI_AVAILABLE:
            print("Brak karmazyn_phi")
        else:
            phi = PhiSpace()
            psk = os.environ.get("KARM_PSK","").encode() or None
            c   = KarmazynCluster(phi, port=opt.port, psk=psk).start()
            if opt.join:
                c.join(opt.join, opt.port)
            print(f"Węzeł {c.local_id} aktywny. Ctrl+C aby zatrzymać.")
            try:
                while True: time.sleep(1)
            except KeyboardInterrupt:
                c.stop()
    else:
        ap.print_help()