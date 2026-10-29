"""PhiSpace.start_loop / stop_loop: jeden wątek naraz, błąd nie blokuje startu."""
from __future__ import annotations

import os
import sys
import threading
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "software")]

from karmazyn_phi import PhiSpace  # noqa: E402


def _wait(cond, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


class PhiLoopTests(unittest.TestCase):
    def test_restart_after_slow_stop_runs_one_worker(self):
        # step() dłuższy niż join(timeout=1.0) w stop_loop
        phi = PhiSpace()
        active = []
        peak = [0]
        lock = threading.Lock()
        release = threading.Event()

        def slow_step(*_a, **_k):
            with lock:
                active.append(1)
                peak[0] = max(peak[0], len(active))
            release.wait(1.5)
            with lock:
                active.pop()
            return iter(())

        phi.step = slow_step
        phi.start_loop(interval=0.01)
        self.assertTrue(_wait(lambda: len(active) == 1))
        old = phi._loop_thread
        phi.stop_loop()                     # join się nie doczeka
        self.assertTrue(old.is_alive())
        phi.start_loop(interval=0.01)
        release.set()
        self.assertTrue(_wait(lambda: not old.is_alive()))
        time.sleep(0.1)
        phi.stop_loop()
        self.assertLessEqual(peak[0], 1, "stary i nowy wątek robiły step() razem")

    def test_error_in_step_allows_restart(self):
        phi = PhiSpace()
        calls = []

        def bad_step(*_a, **_k):
            calls.append(1)
            raise RuntimeError("boom")

        phi.step = bad_step
        phi.start_loop(interval=0.01)
        self.assertTrue(_wait(lambda: not phi._running))
        n = len(calls)
        phi.start_loop(interval=0.01)
        self.assertTrue(_wait(lambda: len(calls) > n))
        phi.stop_loop()

    def test_second_start_is_noop(self):
        phi = PhiSpace()
        phi.start_loop(interval=0.05)
        first = phi._loop_thread
        phi.start_loop(interval=0.05)
        self.assertIs(phi._loop_thread, first)
        phi.stop_loop()
        self.assertFalse(phi._running)
        self.assertTrue(_wait(lambda: not first.is_alive()))


if __name__ == "__main__":
    unittest.main()
