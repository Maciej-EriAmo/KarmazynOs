#!/usr/bin/env python3
"""
test_substrate.py — zestaw testów silnika KarmazynOS (z sond audytowych)
=========================================================================
Maciej Mazur, Warsaw 2026

Sondy behawioralne z audytów 2026-07 przełożone na trwały zestaw testów.
Czysty stdlib (unittest) — zgodnie z filozofią zero-dep. Testy twarzy HRR
(wektory) są warunkowe: bez numpy → skip, reszta działa w pełni.

Uruchomienie:
    python3 -m unittest test_substrate -v
    python3 test_substrate.py

Pokrycie (numeracja z rejestru ryzyk audytu):
  prawo T×reach  — sierota ginie, korzeń trzyma, resurekcja, cykle
  S1   (v1.2)   — env_of: Bubble | iterowalne[Bubble]; string ≠ kontener
  S2   (v1.2)   — reg jako property z jednorazowym warning; publiczne API
  S3   (v1.2)   — create_bubble(root=True) chroni; worek bez roota nie
  S4/S14 (v1.2) — retained_tomb kanon + alias archived / _archived
  S5            — import_to_bubble: kolizja E nadpisuje (udokumentowane)
  S8   (v1.2)   — invalidacja cache wektora po zmianie E (HRR)
  S12  (v1.2)   — tick_batch (1/tick) vs tryb per_atom
  v1.1          — lock, sentinel value w create_atom, świeży stats,
                  ramka-korzeń (współpraca z exec), clamp T
"""

import threading
import unittest
import warnings

from karmazyn_kernel import (
    Store, Bubble, Atom, conforms, kernel_info,
    T_INIT, T_MAX, T_TOMB, HAS_HRR,
)

# Z T=50 i decay=0.92 atom przekracza T_TOMB=2 po 39 tickach;
# 60 ticków = bezpieczny margines pełnego wystygnięcia.
COOL = 60


class _Clo:
    """Atrapa domknięcia dla hooka env_of (rdzeń nie zna języka)."""
    def __init__(self, env):
        self.env = env


def _env_of_single(v):
    return v.env if isinstance(v, _Clo) else None


def _env_of_deep(v):
    """Front z bogatszymi wartościami: spłaszcza listę/krotkę domknięć (S1)."""
    if isinstance(v, _Clo):
        return v.env
    if isinstance(v, (list, tuple)):
        return [x.env for x in v if isinstance(x, _Clo)]
    return None


# ─── Prawo T × reach ─────────────────────────────────────────────────────────

class TestReachLaw(unittest.TestCase):

    def test_orphan_dies(self):
        s = Store()
        a = s.atom_new("var", "orphan")
        s.settle(COOL)
        self.assertFalse(s.has_atom(a.id))
        self.assertEqual(s.stats()["reaped"], 1)

    def test_root_retains_tomb(self):
        s = Store()
        root = s.bubble_new("root")
        s.set_root(root)
        a = s.atom_new("var", "keep")
        root.bind("keep", a)
        s.settle(COOL)
        self.assertTrue(s.has_atom(a.id))
        self.assertTrue(a.is_dead())                       # zimny...
        self.assertEqual(s.stats()["retained_tomb"], 1)    # ...ale retencja, nie GC

    def test_unset_root_then_reap(self):
        s = Store()
        root = s.bubble_new("root")
        s.set_root(root)
        a = s.atom_new("var", "x")
        root.bind("x", a)
        s.settle(COOL)
        self.assertTrue(s.has_atom(a.id))
        s.unset_root(root)
        s.settle(2)
        self.assertFalse(s.has_atom(a.id))

    def test_resurrection_out_of_retention(self):
        s = Store()
        root = s.bubble_new("root")
        s.set_root(root)
        a = s.atom_new("var", "z")
        root.bind("z", a)
        s.settle(COOL)
        self.assertEqual(s.stats()["retained_tomb"], 1)
        for _ in range(12):
            s.heat(a)                                      # ożywienie
        s.tick()
        self.assertFalse(a.is_dead())
        self.assertEqual(s.stats()["retained_tomb"], 0)

    def test_closure_env_of_survives(self):
        s = Store(env_of=_env_of_single)
        root = s.bubble_new("root")
        s.set_root(root)
        inner = s.bubble_new("inner")                      # NIE-korzeń
        n = s.atom_new("var", "n", value=0)
        inner.bind("n", n)
        clo = s.atom_new("var", "clo", value=_Clo(inner))
        root.bind("clo", clo)
        s.settle(100)
        self.assertTrue(s.has_atom(n.id))                  # żyje przez env_of
        self.assertIs(inner.lookup("n"), n)

    def test_parent_cycle_no_recursion(self):
        s = Store(env_of=_env_of_single)
        a_b = s.bubble_new("A")
        b_b = s.bubble_new("B", parent=a_b)
        a_b.parent = b_b                                   # cykl parent
        s.set_root(a_b)
        atom = s.atom_new("var", "cyc", value=_Clo(a_b))   # env_of wraca w cykl
        b_b.bind("cyc", atom)
        s.settle(5)                                        # nie może wybuchnąć
        self.assertTrue(s.has_atom(atom.id))

    def test_extra_reach_protects(self):
        held = set()
        s = Store(extra_reach=lambda: held)
        a = s.atom_new("var", "flat")
        held.add(a.id)
        s.settle(COOL)
        self.assertTrue(s.has_atom(a.id))
        held.clear()
        s.settle(2)
        self.assertFalse(s.has_atom(a.id))


# ─── S1: deep reach przez env_of (v1.2) ──────────────────────────────────────

class TestS1DeepEnvOf(unittest.TestCase):

    def test_iterable_of_bubbles(self):
        s = Store(env_of=_env_of_deep)
        root = s.bubble_new("root")
        s.set_root(root)
        e1, e2 = s.bubble_new("e1"), s.bubble_new("e2")
        x = s.atom_new("var", "x", value=1)
        y = s.atom_new("var", "y", value=2)
        e1.bind("x", x)
        e2.bind("y", y)
        pair = s.atom_new("var", "pair", value=[_Clo(e1), _Clo(e2)])
        root.bind("pair", pair)
        s.settle(100)
        # dawna sonda 22 (false reap) — teraz OBA env żyją
        self.assertTrue(s.has_atom(x.id))
        self.assertTrue(s.has_atom(y.id))

    def test_single_bubble_still_works(self):
        s = Store(env_of=lambda v: v if isinstance(v, Bubble) else None)
        root = s.bubble_new("root")
        s.set_root(root)
        env = s.bubble_new("env")
        held = s.atom_new("var", "held")
        env.bind("held", held)
        ref = s.atom_new("var", "ref", value=env)          # wartość = sam Bubble
        root.bind("ref", ref)
        s.settle(COOL)
        self.assertTrue(s.has_atom(held.id))

    def test_string_is_not_container(self):
        # env_of zwraca string — nie może być iterowany jako kontener Bubbli
        s = Store(env_of=lambda v: "not-a-bubble")
        root = s.bubble_new("root")
        s.set_root(root)
        a = s.atom_new("var", "a")
        root.bind("a", a)
        s.settle(3)                                        # nie może wybuchnąć
        self.assertTrue(s.has_atom(a.id))

    def test_garbage_in_iterable_ignored(self):
        s = Store(env_of=lambda v: [None, 42, "x"] if v == "junk" else None)
        root = s.bubble_new("root")
        s.set_root(root)
        a = s.atom_new("var", "a", value="junk")
        root.bind("a", a)
        s.settle(3)
        self.assertTrue(s.has_atom(a.id))


# ─── Scope / lifecycle ───────────────────────────────────────────────────────

class TestLifecycle(unittest.TestCase):

    def test_delete_atom_purges_bindings(self):
        s = Store()
        b1, b2 = s.bubble_new("b1"), s.bubble_new("b2")
        a = s.atom_new("var", "a")
        b1.bind("a", a)
        b2.bind("alias", a)
        self.assertTrue(s.delete_atom(a.id))
        self.assertNotIn("a", b1.bindings)
        self.assertNotIn("alias", b2.bindings)
        self.assertFalse(s.delete_atom(a.id))              # drugi raz: False

    def test_bind_cross_store_raises(self):
        s1, s2 = Store(), Store()
        b = s1.bubble_new("b")
        foreign = s2.atom_new("var", "f")
        with self.assertRaises(ValueError):
            b.bind("f", foreign)

    def test_bind_non_atom_raises(self):
        s = Store()
        b = s.bubble_new("b")
        with self.assertRaises(TypeError):
            b.bind("x", object())

    def test_shadowing(self):
        s = Store(thermal=False)
        parent = s.bubble_new("parent")
        child = s.bubble_new("child", parent=parent)
        pa = s.atom_new("var", "x", value="parent")
        ca = s.atom_new("var", "x", value="child")
        parent.bind("x", pa)
        child.bind("x", ca)
        self.assertIs(child.lookup("x"), ca)
        self.assertIs(parent.lookup("x"), pa)              # parent nietknięty

    def test_thermal_false_no_decay_no_heat(self):
        s = Store(thermal=False)
        b = s.bubble_new("b")
        a = s.atom_new("var", "a")
        b.bind("a", a)
        t0 = a.T
        s.settle(50)
        b.lookup("a")
        self.assertEqual(a.T, t0)                          # zero decay, zero heat

    def test_no_dangling_after_gc(self):
        s = Store(env_of=_env_of_single)
        root = s.bubble_new("root")
        s.set_root(root)
        for i in range(30):
            frame = s.bubble_new("call")
            arg = s.atom_new("arg", f"p{i}", value=i)
            frame.bind(f"p{i}", arg)                       # ramki bez roota → giną
        s.settle(COOL)
        dangling = sum(1 for b in s.bubbles
                       for aid in b.bindings.values()
                       if s.get_atom(aid) is None)
        self.assertEqual(dangling, 0)
        self.assertEqual(s.stats()["reaped"], 30)


# ─── Dual API (AtomStore) — S3 / S5 / sentinel ───────────────────────────────

class TestAtomStoreAdapter(unittest.TestCase):

    def test_conforms(self):
        self.assertEqual(conforms(Store()), [])

    def test_duplicate_id_raises_and_generator_catches_up(self):
        s = Store()
        s.create_atom("a99", "S", "E")
        with self.assertRaises(ValueError):
            s.create_atom("a99", "S", "E")
        nxt = s.atom_new("var", "next")
        self.assertEqual(nxt.id, "a100")                   # generator dogonił

    def test_value_sentinel(self):
        s = Store()
        s.create_atom("m1", "S", "E", metadata={"v": "cenne"})
        self.assertEqual(s.get_atom("m1").metadata["v"], "cenne")
        s.create_atom("m2", "S", "E", metadata={"v": "cenne"}, value="jawne")
        self.assertEqual(s.get_atom("m2").metadata["v"], "jawne")
        s.create_atom("m3", "S", "E")
        self.assertIsNone(s.get_atom("m3").metadata["v"])

    def test_s3_box_without_root_dies(self):
        s = Store()
        s.create_atom("d1", "doc", "dok1")
        s.create_bubble("box", atom_ids=["d1"])            # BEZ root
        s.settle(COOL)
        self.assertFalse(s.has_atom("d1"))                 # pułapka — udokumentowana

    def test_s3_box_with_root_retains(self):
        s = Store()
        s.create_atom("d2", "doc", "dok2")
        s.create_bubble("box2", atom_ids=["d2"], root=True)
        s.settle(COOL)
        self.assertTrue(s.has_atom("d2"))                  # root=True chroni
        self.assertGreaterEqual(s.stats()["retained_tomb"], 1)

    def test_s5_import_collision_E_overwrites(self):
        s = Store()
        s.create_atom("k1", "S", "toSamoE")
        s.create_atom("k2", "S", "toSamoE")
        s.create_bubble("bag", root=True)
        s.import_to_bubble("bag", "k1")
        s.import_to_bubble("bag", "k2")                    # kolizja E → nadpisanie
        bag = s.get_bubble("bag")
        self.assertEqual(bag.bindings["toSamoE"], "k2")    # udokumentowane (S5)


# ─── S2: enkapsulacja rejestru ───────────────────────────────────────────────

class TestS2Encapsulation(unittest.TestCase):

    def test_reg_property_warns_once(self):
        Store._reg_warned = False                          # reset flagi klasowej
        s = Store()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _ = s.reg
            _ = s.reg
        self.assertEqual(sum(1 for x in w
                             if issubclass(x.category, UserWarning)), 1)
        self.assertIs(s.reg, s._reg)                       # alias, nie kopia

    def test_public_api_covers_reg_usage(self):
        s = Store()
        a = s.atom_new("var", "pub")
        self.assertTrue(s.has_atom(a.id))
        self.assertIs(s.get_atom(a.id), a)
        self.assertIn(a, s.atoms())
        self.assertEqual(s.atoms("WARM"), [a])
        self.assertTrue(s.delete_atom(a.id))


# ─── S4/S14: retained_tomb kanon + aliasy ────────────────────────────────────

class TestS4RetainedTomb(unittest.TestCase):

    def test_stats_keys_and_alias(self):
        s = Store()
        root = s.bubble_new("root")
        s.set_root(root)
        a = s.atom_new("var", "r")
        root.bind("r", a)
        s.settle(COOL)
        st = s.stats()
        self.assertEqual(st["retained_tomb"], 1)
        self.assertEqual(st["archived"], st["retained_tomb"])
        self.assertIs(s._archived, s._retained_tomb)       # ten sam set

    def test_stats_fresh_between_ticks(self):
        s = Store()
        root = s.bubble_new("root")
        s.set_root(root)
        a = s.atom_new("var", "f")
        root.bind("f", a)
        s.settle(COOL)
        self.assertEqual(s.stats()["retained_tomb"], 1)
        for _ in range(12):
            a.touch()                                      # ożywienie BEZ ticka
        self.assertEqual(s.stats()["retained_tomb"], 0)    # świeży licznik (v1.1)


# ─── S12: eventy ticka ───────────────────────────────────────────────────────

class TestS12TickEvents(unittest.TestCase):

    def test_batch_mode_default(self):
        s = Store()
        batches, per_atom = [], []
        s.events.on("tick_batch", batches.append)
        s.events.on("tick", per_atom.append)
        for _ in range(5):
            s.atom_new("var", "e")
        s.tick()
        self.assertEqual(len(batches), 1)                  # JEDEN event / tick
        self.assertEqual(len(per_atom), 0)
        self.assertEqual(batches[0]["atoms"], 5)

    def test_per_atom_mode(self):
        s = Store(tick_event_mode="per_atom")
        per_atom, batches = [], []
        s.events.on("tick", per_atom.append)
        s.events.on("tick_batch", batches.append)
        for _ in range(4):
            s.atom_new("var", "e")
        s.tick()
        self.assertEqual(len(per_atom), 4)                 # tryb wsteczny
        self.assertEqual(len(batches), 0)

    def test_invalid_mode_raises(self):
        with self.assertRaises(ValueError):
            Store(tick_event_mode="cokolwiek")

    def test_batch_reports_reaped(self):
        s = Store()
        got = []
        s.events.on("tick_batch", got.append)
        s.atom_new("var", "sierota")
        s.settle(COOL)
        self.assertEqual(sum(g["reaped"] for g in got), 1)

    def test_vacuum_and_created_events(self):
        s = Store()
        created, vacuumed = [], []
        s.events.on("atom_created", created.append)
        s.events.on("vacuum_decay", vacuumed.append)
        a = s.atom_new("var", "ev")
        s.settle(COOL)
        self.assertEqual([x.id for x in created], [a.id])
        self.assertEqual([x.id for x in vacuumed], [a.id])


# ─── S8: cache wektora HRR (warunkowo — numpy) ───────────────────────────────

@unittest.skipUnless(HAS_HRR, "brak numpy — twarz HRR nieaktywna (zero-dep)")
class TestS8VectorCache(unittest.TestCase):

    def test_invalidate_on_E_change(self):
        import numpy as np
        s = Store()
        a = s.atom_new("var", "stara_nazwa")
        v1 = s.atom_vector(a).copy()
        a.E = "zupelnie_inna_nazwa"
        v2 = s.atom_vector(a)
        self.assertFalse(np.allclose(v1, v2))              # koniec stale cache

    def test_registered_vector_untouched(self):
        import numpy as np
        s = Store()
        a = s.atom_new("var", "nazwa")
        custom = np.ones(2048)
        a.vector = custom                                  # rejestracja ręczna
        v = s.atom_vector(a)
        self.assertIs(v, custom)                           # Store nie nadpisuje
        a.E = "inna"
        self.assertIs(s.atom_vector(a), custom)            # dalej nietknięty

    def test_resonance_after_rename(self):
        # Wektory nazw sa hashowe (sha256->seed), wiec podobienstwo istnieje
        # tylko dla IDENTYCZNEGO E. Ze stale cache zapytanie o NOWA nazwe
        # dawaloby sim≈0 (stary wektor); po invalidacji sim≈1.0.
        s = Store()
        b = s.atom_new("var", "cos_innego")
        s.atom_vector(b)                                   # policz stary wektor
        b.E = "kot dachowy"
        hits = s.resonance("kot dachowy", k=1, threshold=0.9)
        self.assertTrue(hits)
        self.assertEqual(hits[0][1], b.id)                 # rename widoczny w rezonansie


# ─── v1.1: lock / ramki / clamp — regresja ───────────────────────────────────

class TestV11Regression(unittest.TestCase):

    def test_temp_root_frame_protects_args(self):
        # wzorzec z karmazyn_exec._apply: ramka jako tymczasowy korzeń
        s = Store()
        root = s.bubble_new("repl")
        s.set_root(root)
        with s.lock:
            frame = s.bubble_new("call", parent=root)
            s.set_root(frame)
            arg = s.atom_new("arg", "tmp", value=42)
            frame.bind("tmp", arg)
        s.settle(COOL)                                     # scheduler w trakcie "wywołania"
        self.assertTrue(s.has_atom(arg.id))
        s.unset_root(frame)
        s.settle(3)
        self.assertFalse(s.has_atom(arg.id))               # po powrocie: normalny reap

    def test_touch_negative_clamped(self):
        a = Atom("t", T=50.0)
        a.touch(weight=-20)
        self.assertEqual(a.T, 0.0)                         # inwariant 0..T_MAX
        a.heat(-999)
        self.assertEqual(a.T, 0.0)
        a.heat(9999)
        self.assertEqual(a.T, T_MAX)

    def test_thread_hammer_smoke(self):
        s = Store()
        root = s.bubble_new("root")
        s.set_root(root)
        stop = threading.Event()

        def hammer():
            while not stop.is_set():
                s.tick()

        th = threading.Thread(target=hammer, daemon=True)
        th.start()
        try:
            for i in range(300):
                a = s.atom_new("var", f"v{i}", value=i)
                root.bind(f"v{i}", a)
                self.assertIs(root.lookup(f"v{i}"), a)
        finally:
            stop.set()
            th.join(timeout=2)
        dangling = sum(1 for b in s.bubbles
                       for aid in b.bindings.values()
                       if s.get_atom(aid) is None)
        self.assertEqual(dangling, 0)
        self.assertEqual(len(root.bindings), 300)          # nic nie zginęło pod ogniem

    def test_settle_negative_is_noop(self):
        s = Store()
        s.atom_new("var", "n")
        before = s.stats()
        s.settle(-5)                                       # udokumentowany cichy no-op
        self.assertEqual(s.stats(), before)

    def test_kernel_info_declares_contracts(self):
        i = kernel_info()
        self.assertIn("env_of", i["contracts"])
        self.assertIn("retained_tomb", i["open_seams"])
        s = Store()
        for m in i["surfaces"]["engine_native"]:
            self.assertTrue(callable(getattr(s, m, None)), m)


if __name__ == "__main__":
    unittest.main(verbosity=2)
