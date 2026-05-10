import os
import shutil
import tempfile
import numpy as np
import pytest
from karmazyn import KarmazynOS
from soul_store import save_soul, _read_records

class TestSoulStore:
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.ko = KarmazynOS()
        # Initialize some basic state
        label = self.ko.write("Test content for save_soul test")
        self.ko.consolidate(label)

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_soul_success(self):
        """Test successful save_soul execution and file creation"""
        result = save_soul(self.ko, self.temp_dir)

        # Verify success return value
        assert result is True

        soul_path = os.path.join(self.temp_dir, "session.soul")
        npz_path = os.path.join(self.temp_dir, "vectors.npz")

        # Verify files were created
        assert os.path.exists(soul_path)
        assert os.path.exists(npz_path)

        # Inspect session.soul
        records = _read_records(soul_path)
        assert len(records) > 0

        # Check metadata record
        meta_record = records[0]
        assert meta_record["type"] == "meta"
        assert "soul_version" in meta_record
        assert "karmazyn_version" in meta_record

        # Check for at least one bubble record
        bubble_records = [r for r in records if r.get("type") == "bubble"]
        assert len(bubble_records) > 0

        # Inspect vectors.npz
        npz = np.load(npz_path, allow_pickle=True)
        files = list(npz.files)

        # Check that we have vector keys (either sem__ or str__)
        vector_keys = [f for f in files if f.startswith("sem__") or f.startswith("str__")]
        assert len(vector_keys) > 0

    def test_save_soul_error_handling(self):
        """Test save_soul error handling by mocking file permission error"""
        from unittest.mock import patch

        with patch("builtins.open") as mock_open:
            mock_open.side_effect = PermissionError("Mocked permission error")
            result = save_soul(self.ko, self.temp_dir)
            assert result is False
