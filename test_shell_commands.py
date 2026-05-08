import unittest
from unittest.mock import MagicMock, patch
import sys

# Mock all dependencies of shell.py to avoid missing packages and actual system calls
m_runtime = MagicMock()
sys.modules['runtime'] = m_runtime
sys.modules['karmazyn_fs'] = MagicMock()
sys.modules['karmazyn_ui'] = MagicMock()
sys.modules['karmazyn_ui.theme'] = MagicMock()
sys.modules['karmazyn_ui.gfx'] = MagicMock()
sys.modules['bedit'] = MagicMock()
sys.modules['bubble_commands'] = MagicMock()
sys.modules['command_engine'] = MagicMock()
sys.modules['karmazyn_lang'] = MagicMock()
sys.modules['karmazyn_lua'] = MagicMock()

import shell

class TestCmdStabilizuj(unittest.TestCase):
    def setUp(self):
        # Reset RUNTIME mock which is a global in shell
        shell.RUNTIME = MagicMock()
        shell.RUNTIME.resources = {"żywica": 10}
        shell.RUNTIME.current_mission = None

    def test_stabilizuj_no_args(self):
        """Test STABILIZUJ without arguments returns usage info."""
        result = shell.cmd_stabilizuj([])
        self.assertEqual(result, "STABILIZUJ <id>")

    def test_stabilizuj_success_no_mission(self):
        """Test STABILIZUJ success case when not on a mission (resin not consumed)."""
        shell.RUNTIME.current_mission = None
        shell.RUNTIME.resources = {"żywica": 10}
        result = shell.cmd_stabilizuj(["atom1"])
        shell.RUNTIME.stabilize_atom.assert_called_with("atom1")
        self.assertIn("Stabilizowano atom1", result)
        # Resin remains 10 because current_mission is None
        self.assertIn("Żywica: 10", result)
        self.assertEqual(shell.RUNTIME.resources["żywica"], 10)

    def test_stabilizuj_success_no_mission_no_resin_key(self):
        """Test STABILIZUJ success case when resin key is missing (shows infinity)."""
        shell.RUNTIME.current_mission = None
        shell.RUNTIME.resources = {}
        result = shell.cmd_stabilizuj(["atom1"])
        self.assertIn("Żywica: ∞", result)

    def test_stabilizuj_success_with_mission(self):
        """Test STABILIZUJ success case when on a mission (consumes resin)."""
        shell.RUNTIME.current_mission = {"id": "mission1"}
        shell.RUNTIME.resources["żywica"] = 5
        result = shell.cmd_stabilizuj(["atom1"])
        shell.RUNTIME.stabilize_atom.assert_called_with("atom1")
        self.assertEqual(shell.RUNTIME.resources["żywica"], 4)
        self.assertIn("Stabilizowano atom1", result)
        self.assertIn("Żywica: 4", result)

    def test_stabilizuj_no_resin(self):
        """Test STABILIZUJ failure when resin is depleted during a mission."""
        shell.RUNTIME.current_mission = {"id": "mission1"}
        shell.RUNTIME.resources["żywica"] = 0
        result = shell.cmd_stabilizuj(["atom1"])
        self.assertEqual(result, "Brak Żywicy!")
        shell.RUNTIME.stabilize_atom.assert_not_called()

    def test_stabilizuj_value_error(self):
        """Test STABILIZUJ handling of ValueError (e.g. non-existent atom)."""
        shell.RUNTIME.stabilize_atom.side_effect = ValueError("Atom 'unknown' nie istnieje")
        result = shell.cmd_stabilizuj(["unknown"])
        self.assertEqual(result, "Atom 'unknown' nie istnieje")

if __name__ == '__main__':
    unittest.main()
