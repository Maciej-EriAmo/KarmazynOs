"""Zgodność natywnego KAFD (Rust) z DBase/karmazyn_kafd.py.

  python native/karmazyn_kafd/cross/cross_check.py [ścieżka do DBase]

1. Python zapisuje py_* (czas zamrożony: 1700000000, "2023-11-14 22:13").
2. Rust (`cargo run --example kafd_cross write`) zapisuje rust_* z tymi samymi danymi.
3. Bajty: py_v20 == rust_v20, py_v21 == rust_v21, flow, dziennik, compact.
4. Python czyta pliki Rusta; Rust czyta pliki Pythona (`kafd_cross read`)
   i opis musi się zgadzać z tym, co widzi Python.
Exit 0 = zgodne.
"""
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CRATE = os.path.dirname(HERE)
DBASE = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
    "KARMAZYN_DBASE", r"C:\Users\drwis\DBase")
sys.path.insert(0, DBASE)
os.environ["KARMAZYN_KAFD_PLAIN"] = "1"   # część jawna; szyfrowanie jawnie encrypt=True
# klucz węzła dla obu stron (Rust bierze go z tej samej zmiennej)
os.environ["CYNOBER_MASTER_KEY"] = "07" * 32

import karmazyn_cipher as C  # noqa: E402
import karmazyn_kafd as K  # noqa: E402

UNIX = 1700000000
CREATED = "2023-11-14 22:13"


class _FrozenTime:
    @staticmethod
    def time():
        return float(UNIX)

    @staticmethod
    def strftime(_fmt, *_a):
        return CREATED


K.time = _FrozenTime


def thermal():
    d = bytes([2, 0]) + struct.pack("<QQI", UNIX, 417, 0) + struct.pack("<ff", 40.0, 70.0)
    return d + b"rest-of-frame"


def atoms():
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    return [
        K.KAFDAtom("doc.readme", b"Dokumentacja KarmazynOS\n", mime="text/plain", T=45.0),
        K.KAFDAtom("img.logo", png, mime="image/png", T=72.0),
        K.KAFDAtom("shell.init", b'{"id": "shell.init", "S": "sys"}',
                   mime="application/x-phi-atom", T=85.0, atype=K.A_PHI_ATOM),
        K.KAFDAtom("tick.417", thermal(), mime=K.MIME_THERMAL, T=55.5, atype=K.A_THERMAL),
        K.KAFDAtom("ąę.utf", b"x", mime="text/plain", T=12.25),
    ]


META = {"label": "cross", "opis": "żółw"}


def write_py(d):
    for name, layout in (("py_v20.kafd", "table_first"), ("py_v21.kafd", "footer")):
        w = K.KAFDWriter(meta=dict(META), layout=layout)
        for a in atoms():
            w.add(a)
        open(os.path.join(d, name), "wb").write(w.build())
    f = K.KAFDFlowWriter(meta=dict(META))
    for a in atoms():
        f.add(a)
    with open(os.path.join(d, "py_flow.kafs"), "wb") as out:
        f.write_stream(out)
    jp = os.path.join(d, "py_journal.kafs")
    j = K.KAFDJournal(jp, fsync=False, meta={"world": "cross"}, encrypt=False)
    a = atoms()
    j.append_atom(a[3])
    j.append_atom(a[0])
    j.checkpoint(417, "seal", 40.0, 70.0, 0)
    j.close(write_end=False)
    cj = os.path.join(d, "py_compact_src.kafs")
    shutil.copy(jp, cj)
    K.compact_journal(cj, os.path.join(d, "py_compact.kafd"),
                      meta={"source": "kafs-journal", "frames": 2}, encrypt=False)

    # KAFX ze stałym nonce (05×12), żeby porównać bajty z Rustem
    real = C.secrets.token_bytes
    C.secrets.token_bytes = lambda n: b"\x05" * n
    try:
        v21 = open(os.path.join(d, "py_v21.kafd"), "rb").read()
        open(os.path.join(d, "py_kafx.kafd"), "wb").write(C.wrap_kafx(v21, "cross"))
    finally:
        C.secrets.token_bytes = real
    ep = os.path.join(d, "py_enc_journal.kafs")
    j = K.KAFDJournal(ep, fsync=False, meta={"world": "cross"}, world="cross_enc", encrypt=True)
    j.append_atom(a[3])
    j.append_atom(a[0])
    j.checkpoint(417, "seal", 40.0, 70.0, 0)
    j.close(write_end=False)
    ec = os.path.join(d, "py_enc_compact_src.kafs")
    shutil.copy(ep, ec)
    K.compact_journal(ec, os.path.join(d, "py_enc_compact.kafd"),
                      meta={"source": "kafs-journal", "frames": 2},
                      world="cross_enc", encrypt=True)


def describe(a):
    return {"id": a.id, "mime": a.mime, "T": a.T, "T_max": a.T_max,
            "state": a.state_byte, "atype": a.atype, "data": a.data.hex()}


def py_view(d):
    out = {}
    for name in ("py_v20.kafd", "py_v21.kafd", "py_compact.kafd",
                 "py_kafx.kafd", "py_enc_compact.kafd"):
        r = K.KAFDReader.from_path(os.path.join(d, name), use_mmap=False)
        ids = sorted(r.atom_ids)
        out[name] = {
            "version": struct.unpack(">H", bytes(r._data[4:6]))[0],
            "flags": r._flags, "meta": r.meta,
            "atoms": [describe(r.get_atom(i)) for i in ids],
            "ticks": [{"tick": t["tick"], "T_min": t["T_min"], "T_max": t["T_max"],
                       "kind": t["kind"]} for t in r.tick_index],
        }
        r.close()
    with open(os.path.join(d, "py_flow.kafs"), "rb") as f:
        fr = K.KAFDFlowReader(f)
        fr.read_header()
        flow = [describe(a) for a in fr.iter_atoms()]
        out["py_flow.kafs"] = {"meta": fr.meta, "atoms": flow}
    for name, world, enc in (("py_journal.kafs", None, False),
                             ("py_enc_journal.kafs", "cross_enc", True)):
        j = K.KAFDJournal(os.path.join(d, name), fsync=False, world=world, encrypt=enc)
        ck = j.last_checkpoint
        out[name] = {
            "frames": j.n_frames, "last_tick": j.last_tick,
            "checkpoint": {"tick": ck["tick"], "n_frames": ck["n_frames"],
                           "causality": ck["causality"]},
            "atoms": [describe(a) for a in j.iter_atoms()],
        }
        j.close()
    return out


def cargo(*args):
    env = dict(os.environ)
    if os.name == "nt" and not shutil.which("link.exe") and "RUSTUP_TOOLCHAIN" not in env:
        env["RUSTUP_TOOLCHAIN"] = "stable-x86_64-pc-windows-gnu"
    r = subprocess.run(["cargo", "run", "--quiet", "--release", "--example", "kafd_cross", "--", *args],
                       cwd=CRATE, env=env, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout, r.stderr)
        raise SystemExit(f"cargo {args[0]} nie przeszło")
    return r.stdout


def main():
    d = tempfile.mkdtemp(prefix="kafd_cross_")
    fails = []
    try:
        write_py(d)
        cargo("write", d)

        for py, rs in (("py_v20.kafd", "rust_v20.kafd"), ("py_v21.kafd", "rust_v21.kafd"),
                       ("py_flow.kafs", "rust_flow.kafs"), ("py_journal.kafs", "rust_journal.kafs"),
                       ("py_compact.kafd", "rust_compact.kafd"),
                       ("py_kafx.kafd", "rust_kafx.kafd")):
            a = open(os.path.join(d, py), "rb").read()
            b = open(os.path.join(d, rs), "rb").read()
            ok = a == b
            print(f"{'OK  ' if ok else 'BŁĄD'} bajty {py} == {rs} ({len(a)} B / {len(b)} B)")
            if not ok:
                fails.append(f"bajty {py}")
                for i, (x, y) in enumerate(zip(a, b)):
                    if x != y:
                        print(f"     pierwsza różnica @ {i}: py={a[i:i+16].hex()} rs={b[i:i+16].hex()}")
                        break

        # Python czyta pliki Rusta (w tym compact z czasem „teraz”)
        for name in ("rust_v20.kafd", "rust_v21.kafd", "rust_compact_now.kafd"):
            r = K.KAFDReader.from_path(os.path.join(d, name), use_mmap=False)
            got = {i: r.get_atom(i).data for i in r.atom_ids}
            r.close()
            want = 5 if "compact" not in name else 2
            ok = len(got) == want
            print(f"{'OK  ' if ok else 'BŁĄD'} Python czyta {name}: {len(got)} atomów")
            if not ok:
                fails.append(f"python czyta {name}")

        # szyfrowane pliki Rusta: Python odszyfrowuje, bez jawnej treści na dysku
        for name in ("rust_enc_journal.kafs", "rust_enc_compact.kafd"):
            raw = open(os.path.join(d, name), "rb").read()
            if b"Dokumentacja" in raw:
                fails.append(f"jawna treść w {name}")
                print(f"BŁĄD jawna treść w {name}")
        j = K.KAFDJournal(os.path.join(d, "rust_enc_journal.kafs"), fsync=False,
                          world="cross_enc", encrypt=True)
        got = [a.data for a in j.iter_atoms()]
        ok = got == [thermal(), b"Dokumentacja KarmazynOS\n"] and j.last_tick == 417
        j.close()
        print(f"{'OK  ' if ok else 'BŁĄD'} Python odszyfrowuje dziennik KX1 Rusta (tick {j.last_tick})")
        if not ok:
            fails.append("python czyta rust_enc_journal")
        r = K.KAFDReader.from_path(os.path.join(d, "rust_enc_compact.kafd"), use_mmap=False)
        ok = (r.get_atom("doc.readme").data == b"Dokumentacja KarmazynOS\n"
              and r._flags & K.F_ENCRYPTED)
        print(f"{'OK  ' if ok else 'BŁĄD'} Python odszyfrowuje compact KAFX Rusta")
        if not ok:
            fails.append("python czyta rust_enc_compact")

        # Rust czyta pliki Pythona — opis jak u Pythona
        rust = json.loads(cargo("read", d))
        py = py_view(d)
        for name in py:
            ok = rust.get(name) == py[name]
            print(f"{'OK  ' if ok else 'BŁĄD'} Rust czyta {name} jak Python")
            if not ok:
                fails.append(f"rust czyta {name}")
                print("     py:  ", json.dumps(py[name], ensure_ascii=False)[:400])
                print("     rust:", json.dumps(rust.get(name), ensure_ascii=False)[:400])
    finally:
        shutil.rmtree(d, ignore_errors=True)
    if fails:
        print("KAFD CROSS FAIL:", ", ".join(fails))
        return 1
    print("KAFD CROSS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
