# -*- coding: utf-8 -*-
"""identity.bin v3 (DPAPI / hasło / jawny) i session.soul bez p2s.

Tożsamość: zapis i odczyt w każdym schemacie, złe hasło, migracja v2→v3.
Sesja: plik nie zawiera p2s ani treści bąbli; nowy węzeł odtwarza je
z identity.bin; obca tożsamość nie wczytuje; format 1.0.0 nadal działa.
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import _path  # noqa: F401

import karmazyn_identity as ki

ROOT = Path(__file__).resolve().parents[1]


class _Env:
    def __init__(self, **kv):
        self.kv = kv
        self.old = {}

    def __enter__(self):
        for k, v in self.kv.items():
            self.old[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def __exit__(self, *exc):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _quiet(fn, *a, **k):
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return fn(*a, **k)


class IdentityFileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.p2s = os.urandom(32)

    def _roundtrip(self, scheme, **env):
        with _Env(KARMAZYN_IDENTITY_SCHEME=scheme, **env):
            _quiet(ki.save_identity, self.p2s, self.dir)
            raw = Path(self.dir, ki.FILENAME).read_bytes()
            got = _quiet(ki.load_identity, self.dir)
        self.assertEqual(got, self.p2s)
        return raw

    @unittest.skipUnless(sys.platform == "win32", "DPAPI tylko na Windows")
    def test_dpapi_roundtrip_hides_key(self):
        raw = self._roundtrip("dpapi")
        self.assertEqual(raw[5], ki.SCHEME_DPAPI)
        self.assertNotIn(self.p2s, raw)

    @unittest.skipUnless(sys.platform == "win32", "DPAPI tylko na Windows")
    def test_dpapi_tampered_is_rejected(self):
        self._roundtrip("dpapi")
        f = Path(self.dir, ki.FILENAME)
        data = bytearray(f.read_bytes())
        data[-5] ^= 0xFF
        f.write_bytes(bytes(data))
        self.assertIsNone(_quiet(ki.load_identity, self.dir))

    def test_passphrase_roundtrip_and_wrong_passphrase(self):
        if ki._aesgcm() is None:
            self.skipTest("brak cryptography")
        raw = self._roundtrip("passphrase", KARMAZYN_IDENTITY_PASSPHRASE="dobre haslo")
        self.assertEqual(raw[5], ki.SCHEME_PASSPHRASE)
        self.assertNotIn(self.p2s, raw)
        with _Env(KARMAZYN_IDENTITY_PASSPHRASE="zle haslo"):
            self.assertIsNone(_quiet(ki.load_identity, self.dir))
        with _Env(KARMAZYN_IDENTITY_PASSPHRASE=None):
            self.assertIsNone(_quiet(ki.load_identity, self.dir))

    def test_plain_warns(self):
        with _Env(KARMAZYN_IDENTITY_SCHEME="plain"):
            err = io.StringIO()
            with redirect_stderr(err):
                ki.save_identity(self.p2s, self.dir)
        self.assertIn("UWAGA", err.getvalue())
        self.assertEqual(_quiet(ki.load_identity, self.dir), self.p2s)

    def test_v2_is_migrated_to_v3(self):
        fp = ki._machine_fingerprint()
        v2 = ki.MAGIC + ki.V2 + fp[:8] + bytes(a ^ b for a, b in zip(self.p2s, fp))
        f = Path(self.dir, ki.FILENAME)
        f.write_bytes(v2)
        with _Env(KARMAZYN_IDENTITY_SCHEME="plain"):
            self.assertEqual(_quiet(ki.load_identity, self.dir), self.p2s)
        self.assertEqual(f.read_bytes()[4:5], ki.V3)
        self.assertEqual(_quiet(ki.load_identity, self.dir), self.p2s)

    def test_v2_from_other_machine_is_none(self):
        bad = ki.MAGIC + ki.V2 + b"\0" * 8 + os.urandom(32)
        Path(self.dir, ki.FILENAME).write_bytes(bad)
        self.assertIsNone(_quiet(ki.load_identity, self.dir))

    def test_missing_file_is_none(self):
        self.assertIsNone(ki.load_identity(self.dir))


def _kernel_and_soul():
    for p in (ROOT / "archiwum", ROOT / "extras"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import importlib

    karmazyn = _quiet(importlib.import_module, "karmazyn")
    spec = importlib.util.spec_from_file_location(
        "soul_store_extras", ROOT / "extras" / "soul_store.py"
    )
    soul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(soul)
    return karmazyn, soul


class SoulFileTests(unittest.TestCase):
    SECRET = b"tajna notatka 42"

    @classmethod
    def setUpClass(cls):
        try:
            cls.karmazyn, cls.soul = _kernel_and_soul()
        except Exception as e:  # numpy / zależności archiwum
            raise unittest.SkipTest(f"brak jądra archiwum: {e}")

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.ko = self._node()
        phi = self.ko.phi
        self.ko.bubbles.store(
            label="note", S_struct=phi.embed_structural(self.SECRET),
            S_sem=phi.embed_semantic(self.SECRET), content_raw=self.SECRET,
            inode="karmazyn://bubbles/note", epoch=0,
        )

    def _node(self):
        return _quiet(self.karmazyn.KarmazynOS)

    def _save(self, ko):
        self.assertTrue(_quiet(self.soul.save_soul, ko, self.dir))

    def _note(self, ko):
        b = ko.bubbles.get_by_label("note")
        return b.decrypt_content() if b else None

    def test_session_has_no_key_or_plaintext(self):
        self._save(self.ko)
        text = Path(self.dir, "session.soul").read_text(encoding="utf-8")
        p2s = self.ko.phi._p2s
        self.assertNotIn(p2s.hex(), text)
        self.assertNotIn(base64.b64encode(p2s).decode(), text)   # bąbel tożsamości
        self.assertNotIn(base64.b64encode(self.SECRET).decode(), text)
        self.assertNotIn('"p2s"', text)
        self.assertIn('"p2s_check"', text)
        self.assertTrue(Path(self.dir, "identity.bin").is_file())

    def test_new_node_restores_from_identity(self):
        self._save(self.ko)
        other = self._node()
        self.assertNotEqual(other.phi._p2s, self.ko.phi._p2s)
        self.assertTrue(_quiet(self.soul.load_soul, other, self.dir))
        self.assertEqual(other.phi._p2s, self.ko.phi._p2s)
        self.assertEqual(self._note(other), self.SECRET)

    def test_foreign_identity_refuses_and_keeps_state(self):
        self._save(self.ko)
        _quiet(ki.save_identity, os.urandom(32), self.dir)
        other = self._node()
        before = dict(other.bubbles._b)
        self.assertFalse(_quiet(self.soul.load_soul, other, self.dir))
        self.assertEqual(other.bubbles._b, before)

    def test_missing_identity_refuses(self):
        self._save(self.ko)
        os.remove(os.path.join(self.dir, "identity.bin"))
        self.assertFalse(_quiet(self.soul.load_soul, self._node(), self.dir))

    def test_legacy_1_0_0_still_loads(self):
        self._save(self.ko)
        path = Path(self.dir, "session.soul")
        recs = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        for r in recs:
            if r["type"] == "meta":
                r.pop("p2s_check")
                r["p2s"] = self.ko.phi._p2s.hex()
            elif r["type"] == "bubble":
                raw = self.ko.bubbles._b[r["id"]].decrypt_content()
                del r["content_enc_b64"]
                r["content_b64"] = base64.b64encode(raw).decode()
        path.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
        os.remove(os.path.join(self.dir, "identity.bin"))
        other = self._node()
        self.assertTrue(_quiet(self.soul.load_soul, other, self.dir))
        self.assertEqual(other.phi._p2s, self.ko.phi._p2s)
        self.assertEqual(self._note(other), self.SECRET)


if __name__ == "__main__":
    unittest.main()
