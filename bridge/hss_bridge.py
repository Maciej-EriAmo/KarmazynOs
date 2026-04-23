#!/usr/bin/env python3
# hss_bridge.py – KarmazynOS LSM Bridge

import os
import sys
import socket
import struct
import time
import hashlib
import hmac
import threading
from typing import Optional

# Zakładamy, że karmazyn.py jest dostępny
from karmazyn import KarmazynOS

HSS_SOCK_PATH = "/run/hss-daemon.sock"
HSS_OP_READ   = 0x01
HSS_OP_WRITE  = 0x02

# Struktura zgodna z definicją C (__packed)
# u64 timestamp_ns; u32 pid; u64 inode_id; u32 op_mask; u32 policy_id;
# u32 agent_id; u64 prism_mask; u8 phi_context; u8 nonce[16];
MSG_FORMAT = "<Q I Q I I I Q B 16s"   # little-endian, packed
RESP_FORMAT = "<16s I I"              # nonce_echo[16], decision, flags

k = KarmazynOS()

def handle_connection(conn):
    try:
        data = conn.recv(1024)
        if not data:
            return
        # Parsowanie
        (ts, pid, inode_id, op_mask, policy_id,
         agent_id, prism_mask, phi_ctx, nonce) = struct.unpack(MSG_FORMAT, data)
        print(f"[LSM] pid={pid} inode={inode_id} op={op_mask} agent={agent_id} phi={phi_ctx}")

        # Wywołanie decyzji KarmazynOS (możemy użyć evaluate lub specjalnej metody)
        # Tutaj uproszczone: zawsze pozwalamy na read, chyba że phi_ctx == 0 (niezaufany)
        decision = 1 if phi_ctx != 0 else 0   # 1 = allow, 0 = deny
        flags = 0

        # Odpowiedź
        resp = struct.pack(RESP_FORMAT, nonce, decision, flags)
        conn.send(resp)
    except Exception as e:
        print(f"Błąd obsługi: {e}")
    finally:
        conn.close()

def main():
    # Usuń stare gniazdo
    try:
        os.unlink(HSS_SOCK_PATH)
    except OSError:
        pass

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(HSS_SOCK_PATH)
    sock.listen(5)
    os.chmod(HSS_SOCK_PATH, 0o666)
    print(f"KarmazynOS LSM Bridge nasłuchuje na {HSS_SOCK_PATH}")

    while True:
        conn, _ = sock.accept()
        t = threading.Thread(target=handle_connection, args=(conn,))
        t.daemon = True
        t.start()

if __name__ == "__main__":
    main()
