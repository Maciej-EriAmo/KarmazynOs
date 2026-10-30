"""Klient Rust ↔ prawdziwy serwer DBase (cynober_server.py) przez TCP.

  python native/karmazyn_cynober/cross/live_check.py [ścieżka do DBase]

Serwer i klient mają osobne katalogi danych (różne node_id, Φ², klucze) —
jak dwie maszyny. Scenariusze: ECDH, HSS standard, HSS production,
PSK (zgodny i zły), seed QKD, kilka zapytań na jednym tunelu,
serwer z CYNOBER_MIN_CRYPTO=hss bez profilu po stronie klienta (odmowa).
Exit 0 = wszystko zgodnie z oczekiwaniem.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CRATE = os.path.dirname(HERE)
DBASE = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
    "KARMAZYN_DBASE", r"C:\Users\drwis\DBase")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def cargo_env():
    env = dict(os.environ)
    link = (shutil.which("link.exe") or "").lower()
    msvc = link and not any(x in link for x in ("msys", "\\git\\", "usr\\bin"))
    if os.name == "nt" and not msvc and "RUSTUP_TOOLCHAIN" not in env:
        env["RUSTUP_TOOLCHAIN"] = "stable-x86_64-pc-windows-gnu"
    return env


def build_client():
    r = subprocess.run(["cargo", "build", "--quiet", "--release", "--example", "cynober_query"],
                       cwd=CRATE, env=cargo_env(), capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout, r.stderr)
        raise SystemExit("build klienta nie przeszedł")
    exe = os.path.join(CRATE, "target", "release", "examples",
                       "cynober_query" + (".exe" if os.name == "nt" else ""))
    return exe


CLEAR = ("KARM_HSS_PROFILE", "KARM_PSK", "KARM_QKD_SEED", "KARM_QKD_PATH", "KARM_QKD_PIPE",
         "CYNOBER_MIN_CRYPTO", "CYNOBER_FORCE_CRYPTO", "KARM_PHI2", "CYNOBER_SECURE_BOOT",
         "CYNOBER_ALLOW_SIMPLE", "CYNOBER_ALLOW_LEGACY")


def run_case(exe, root, name, server_env, client_env, queries):
    port = free_port()
    base = {k: v for k, v in os.environ.items() if k not in CLEAR}
    senv = dict(base, CYNOBER_DATA_HOME=os.path.join(root, name, "server"),
                PYTHONIOENCODING="utf-8", **server_env)
    cenv = dict(base, CYNOBER_DATA_HOME=os.path.join(root, name, "client"), **client_env)
    srv = subprocess.Popen([sys.executable, "cynober_server.py", "127.0.0.1", str(port)],
                           cwd=DBASE, env=senv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, encoding="utf-8", errors="replace")
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                break
            except OSError:
                if srv.poll() is not None:
                    break
                time.sleep(0.2)
        # pierwsze połączenie sondujące serwer zamyka; chwila na sprzątnięcie
        time.sleep(0.3)
        r = subprocess.run([exe, "127.0.0.1", str(port), *queries], env=cenv,
                           capture_output=True, text=True, encoding="utf-8", timeout=120)
        out = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {"error": r.stderr}
    finally:
        srv.terminate()
        try:
            log = srv.communicate(timeout=5)[0]
        except subprocess.TimeoutExpired:
            srv.kill()
            log = srv.communicate()[0]
    return out, log


def results_ok(answer):
    return isinstance(answer, dict) and "results" in answer and answer["results"]


def main():
    exe = build_client()
    root = tempfile.mkdtemp(prefix="cynober_live_")
    fails = []
    hex_seed = "5a" * 32

    cases = [
        ("ecdh", {}, {}, ["ZDROWIE"],
         lambda o: o.get("session", {}).get("crypto_mode") == "ecdh"
         and o["session"]["hsl"] and results_ok(o["answers"][0])),
        ("hss_standard", {"KARM_HSS_PROFILE": "standard"}, {"KARM_HSS_PROFILE": "standard"},
         ["ZDROWIE", "LISTA ŚWIATÓW", "ZDROWIE"],
         lambda o: o.get("session", {}).get("hss_profile") == "standard"
         and all(results_ok(a) for a in o["answers"])),
        ("hss_production", {"KARM_HSS_PROFILE": "production"}, {"KARM_HSS_PROFILE": "production"},
         ["ZDROWIE"],
         lambda o: o.get("session", {}).get("hss_profile") == "production" and results_ok(o["answers"][0])),
        ("psk_ok", {"KARM_PSK": "sekret-sieci"}, {"KARM_PSK": "sekret-sieci"}, ["ZDROWIE"],
         lambda o: o.get("session", {}).get("psk") and results_ok(o["answers"][0])),
        ("psk_zly", {"KARM_PSK": "sekret-sieci"}, {"KARM_PSK": "inny"}, ["ZDROWIE"],
         lambda o: "error" in o),
        ("qkd", {"KARM_QKD_SEED": hex_seed}, {"KARM_QKD_SEED": hex_seed}, ["ZDROWIE"],
         lambda o: o.get("session", {}).get("qkd_hybrid") and results_ok(o["answers"][0])),
        ("qkd_rozjazd", {"KARM_QKD_SEED": hex_seed}, {}, ["ZDROWIE"],
         lambda o: "QKD" in o.get("error", "")),
        ("min_hss_bez_profilu", {"CYNOBER_MIN_CRYPTO": "hss"}, {}, ["ZDROWIE"],
         lambda o: "error" in o),
    ]
    try:
        for name, senv, cenv, queries, check in cases:
            out, log = run_case(exe, root, name, senv, cenv, queries)
            ok = bool(check(out))
            s = out.get("session", {})
            short = (f"{s.get('crypto_mode')}"
                     f"{'/' + s['hss_profile'] if s.get('hss_profile') else ''}"
                     f" hsl={s.get('hsl')} psk={s.get('psk')} qkd={s.get('qkd_hybrid')}"
                     f" {s.get('node_local')}→{s.get('node_remote')}") if s else out.get("error", "")[:120]
            print(f"{'OK  ' if ok else 'BŁĄD'} {name}: {short}")
            if s and out.get("answers"):
                a = out["answers"][0]
                print(f"     odpowiedź: {json.dumps(a, ensure_ascii=False)[:160]}")
            if not ok:
                fails.append(name)
                print("     klient:", json.dumps(out, ensure_ascii=False)[:400])
                print("     serwer:", "\n".join(log.strip().splitlines()[-6:]))
    finally:
        shutil.rmtree(root, ignore_errors=True)
    if fails:
        print("CYNOBER LIVE FAIL:", ", ".join(fails))
        return 1
    print("CYNOBER LIVE PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
