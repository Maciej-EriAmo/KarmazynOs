import pytest
from karmazyn import KarmazynOS
import bubblefs
import os
import json
import numpy as np
from unittest.mock import Mock

def test_bubblefs_export_import(tmp_path):
    ko = KarmazynOS()
    label = ko.write("test bubblefs content")
    bid = ko.consolidate(label)

    export_dir = str(tmp_path / "test_export")

    secret = b"my_secret_key"

    manifest = bubblefs.export(ko, export_dir, shared_secret=secret)

    ko2 = KarmazynOS()
    import_result = bubblefs.import_(ko2, export_dir, shared_secret=secret)

    assert ko2.bubbles._b[bid].bubble_key != ko.bubbles._b[bid].bubble_key
    assert ko2.read_bubble(label) == "test bubblefs content"


def test_export_with_mocks(tmp_path):
    mock_ko = Mock()
    mock_ko.VERSION = "1.0.0"
    mock_ko.phi.epoch = 10
    mock_ko.phi.dim = 512
    mock_ko.phi.t_vacuum.return_value = 1.0
    mock_ko.phi.temperature.return_value = 5.0

    mock_bubble = Mock()
    mock_bubble.id = "b1"
    mock_bubble.label = "lbl1"
    mock_bubble.inode = "inode1"
    mock_bubble.epoch_born = 1
    mock_bubble.recall_count = 0
    mock_bubble.consolidated_from = "origin"
    mock_bubble.metadata = {}
    mock_bubble.decay_start_epoch = None
    mock_bubble.decrypt_content.return_value = b"test content"
    mock_bubble.fingerprint = b"fingerprint"

    mock_bubble.S_struct = np.array([1, 2, 3], dtype=np.float32)
    mock_bubble.S_sem = np.array([4, 5, 6], dtype=np.float32)

    mock_ko.bubbles._b = {"b1": mock_bubble}
    mock_ko.bubbles._rev = set()
    mock_ko.bubbles._idx = {"lbl1": "b1"}

    mock_hologram = Mock()
    mock_hologram.id = "h1"
    mock_hologram.topic = "topic1"
    mock_hologram.proto = np.array([7, 8, 9], dtype=np.float32)
    mock_hologram.generators = [np.array([1, 1, 1], dtype=np.float32)]
    mock_hologram.weights = [1.0]
    mock_hologram.bubble_labels = ["lbl1"]
    mock_hologram.epoch_created = 5
    mock_hologram.decay_rate = 0.001
    mock_hologram.metadata = {}

    mock_ko.holograms = {"h1": mock_hologram}

    mock_ko.phi._sem = {"lbl1": np.array([4, 5, 6], dtype=np.float32)}
    mock_ko.phi._mx.atoms = [
        {"label": "lbl1", "S": np.array([1, 2, 3], dtype=np.float32), "T": 10.0}
    ]

    export_dir = str(tmp_path / "test_mock_export")

    secret = b"my_secret_key"

    manifest = bubblefs.export(mock_ko, export_dir, shared_secret=secret, include_phi_vectors=True)

    assert os.path.exists(export_dir)
    assert os.path.exists(os.path.join(export_dir, "manifest.json"))
    assert os.path.exists(os.path.join(export_dir, "bubbles", "b1.bbl"))
    assert os.path.exists(os.path.join(export_dir, "holograms", "h1.hgm"))
    assert os.path.exists(os.path.join(export_dir, "phi", "sem_vectors.npz"))
    assert os.path.exists(os.path.join(export_dir, "phi", "structural.npz"))

    with open(os.path.join(export_dir, "manifest.json"), "r") as f:
        loaded_manifest = json.load(f)
        assert loaded_manifest["n_bubbles"] == 1
        assert loaded_manifest["n_holograms"] == 1
        assert loaded_manifest["encrypted"] == True

if __name__ == "__main__":
    pytest.main([__file__])
