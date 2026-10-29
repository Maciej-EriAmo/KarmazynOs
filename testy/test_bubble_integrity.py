# -*- coding: utf-8 -*-
"""Integralność bąbli: odcisk HMAC w jądrze i MAC w BubbleFS.

Jądro: podmieniony szyfrogram bąbla nie przechodzi przez decrypt_content.
extras/bubblefs 1.1: eksport bez klucza tylko jawnie, bez bąbla tożsamości,
MAC treści sprawdzany przy imporcie (zły klucz, podmiana, stary eksport).
archiwum/bubblefs: jawny rekord i manifest bez HMAC są odrzucane.
"""
from __future__ import annotations

import base64
import importlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import _path  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
SECRET = b"S" * 32
NOTE = b"tajna notatka 42"


def _quiet(fn, *a, **k):
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return fn(*a, **k)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def setUpModule():
    global karmazyn, bfs_new, bfs_arch
    arch = str(ROOT / "archiwum")
    if arch not in sys.path:
        sys.path.insert(0, arch)
    try:
        karmazyn = _quiet(importlib.import_module, "karmazyn")
    except Exception as e:  # numpy / pycryptodome / zależności archiwum
        raise unittest.SkipTest(f"brak jądra archiwum: {e}")
    bfs_new = _load("bubblefs_extras", ROOT / "extras" / "bubblefs.py")
    bfs_arch = _load("bubblefs_archiwum", ROOT / "archiwum" / "bubblefs.py")


def _node_with_note():
    ko = _quiet(karmazyn.KarmazynOS)
    phi = ko.phi
    _quiet(
        ko.bubbles.store,
        label="note", S_struct=phi.embed_structural(NOTE), S_sem=phi.embed_semantic(NOTE),
        content_raw=NOTE, inode="karmazyn://bubbles/note", epoch=0,
    )
    return ko


def _note(ko):
    b = ko.bubbles.get_by_label("note")
    return b.decrypt_content() if b else None


class KernelFingerprintTests(unittest.TestCase):
    def test_tampered_ciphertext_is_detected(self):
        ko = _node_with_note()
        b = ko.bubbles.get_by_label("note")
        self.assertEqual(b.decrypt_content(), NOTE)
        ct = bytearray(b.encrypted_content)
        ct[0] ^= 0x01                      # bit flip w szyfrze strumieniowym
        b.encrypted_content = bytes(ct)
        with self.assertRaises(karmazyn.BubbleIntegrityError):
            b.decrypt_content()
        self.assertIsNone(_quiet(ko.read_bubble, "note"))

    def test_revoked_bubble_still_returns_noise(self):
        ko = _node_with_note()
        b = ko.bubbles.get_by_label("note")
        b.bubble_key = b""
        self.assertNotEqual(b.decrypt_content(), NOTE)   # bez wyjątku


class BubbleFSExportTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.ko = _node_with_note()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _files(self):
        return [json.loads(p.read_text(encoding="utf-8"))
                for p in Path(self.dir, "bubbles").glob("*.bbl")]

    def _reseal_manifest(self):
        # atakujący przelicza niekluczowany sha256 manifestu
        m = Path(self.dir, "manifest.json")
        data = json.loads(m.read_text(encoding="utf-8"))
        data["integrity_sha256"] = bfs_new._manifest_hash(
            os.path.join(self.dir, "bubbles"), os.path.join(self.dir, "holograms"))
        m.write_text(json.dumps(data), encoding="utf-8")

    def _import(self, secret=SECRET, **kw):
        other = _quiet(karmazyn.KarmazynOS)
        res = _quiet(bfs_new.import_, other, self.dir, shared_secret=secret, **kw)
        return other, res

    def test_plaintext_export_needs_consent(self):
        with self.assertRaises(ValueError):
            _quiet(bfs_new.export, self.ko, self.dir)
        with self.assertRaises(ValueError):
            _quiet(bfs_new.export_single_bubble, self.ko, "note", self.dir)
        _quiet(bfs_new.export, self.ko, self.dir, allow_plaintext=True)
        recs = self._files()
        self.assertEqual([r["label"] for r in recs], ["note"])

    def test_identity_bubble_never_exported(self):
        _quiet(bfs_new.export, self.ko, self.dir, shared_secret=SECRET)
        labels = [r["label"] for r in self._files()]
        self.assertNotIn(bfs_new.IDENTITY_LABEL, labels)
        p2s_b64 = base64.b64encode(self.ko.phi._p2s).decode()
        for p in Path(self.dir).rglob("*"):
            if p.is_file() and p.suffix in (".bbl", ".json"):
                self.assertNotIn(p2s_b64, p.read_text(encoding="utf-8"))
        self.assertIsNone(_quiet(
            bfs_new.export_single_bubble, self.ko, bfs_new.IDENTITY_LABEL, self.dir,
            shared_secret=SECRET))

    def test_roundtrip_with_secret(self):
        _quiet(bfs_new.export, self.ko, self.dir, shared_secret=SECRET)
        other, res = self._import()
        self.assertEqual(res["skipped"], [])
        self.assertEqual(_note(other), NOTE)   # odcisk przeliczony nowym kluczem

    def test_wrong_secret_is_skipped(self):
        _quiet(bfs_new.export, self.ko, self.dir, shared_secret=SECRET)
        other, res = self._import(secret=b"X" * 32)
        self.assertIsNone(other.bubbles.get_by_label("note"))
        self.assertTrue(any("MAC" in s for s in res["skipped"]))

    def test_tampered_content_is_skipped(self):
        _quiet(bfs_new.export, self.ko, self.dir, shared_secret=SECRET)
        f = next(Path(self.dir, "bubbles").glob("*.bbl"))
        rec = json.loads(f.read_text(encoding="utf-8"))
        ct = bytearray(base64.b64decode(rec["content_b64"]))
        ct[0] ^= 0x01
        rec["content_b64"] = base64.b64encode(bytes(ct)).decode()
        f.write_text(json.dumps(rec), encoding="utf-8")
        self._reseal_manifest()
        other, res = self._import()
        self.assertIsNone(other.bubbles.get_by_label("note"))
        self.assertTrue(any("MAC" in s for s in res["skipped"]))

    def test_old_export_without_mac_needs_flag(self):
        _quiet(bfs_new.export, self.ko, self.dir, shared_secret=SECRET)
        f = next(Path(self.dir, "bubbles").glob("*.bbl"))
        rec = json.loads(f.read_text(encoding="utf-8"))
        del rec["content_mac_b64"]
        f.write_text(json.dumps(rec), encoding="utf-8")
        self._reseal_manifest()
        other, res = self._import()
        self.assertIsNone(other.bubbles.get_by_label("note"))
        other, res = self._import(allow_unauthenticated=True)
        self.assertEqual(_note(other), NOTE)

    def test_plaintext_import_needs_consent(self):
        _quiet(bfs_new.export, self.ko, self.dir, allow_plaintext=True)
        other, _res = self._import(secret=None)
        self.assertIsNone(other.bubbles.get_by_label("note"))
        other, _res = self._import(secret=None, allow_plaintext=True)
        self.assertEqual(_note(other), NOTE)


class ArchiveBubbleFSTests(unittest.TestCase):
    def setUp(self):
        if not bfs_arch._CRYPTO_OK:
            self.skipTest("brak cryptography")
        self.dir = tempfile.mkdtemp()
        self.ko = _node_with_note()
        _quiet(bfs_arch.export, self.ko, self.dir, shared_secret=SECRET)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_roundtrip_keeps_content_readable(self):
        other = _quiet(karmazyn.KarmazynOS)
        _quiet(bfs_arch.import_, other, self.dir, shared_secret=SECRET)
        self.assertEqual(_note(other), NOTE)

    def test_plaintext_record_is_rejected(self):
        with self.assertRaises(ValueError):
            bfs_arch._aes_decrypt(bfs_arch._BBL_MAGIC_PLN + b"{}", SECRET, "x",
                                  bfs_arch._BBL_MAGIC_ENC, bfs_arch._BBL_MAGIC_PLN)

    def test_manifest_without_hmac_is_rejected(self):
        m = Path(self.dir, "manifest.json")
        data = json.loads(m.read_text(encoding="utf-8"))
        data.pop("integrity_hmac")
        m.write_text(json.dumps(data), encoding="utf-8")
        other = _quiet(karmazyn.KarmazynOS)
        with self.assertRaises(ValueError):
            _quiet(bfs_arch.import_, other, self.dir, shared_secret=SECRET)


if __name__ == "__main__":
    unittest.main()
