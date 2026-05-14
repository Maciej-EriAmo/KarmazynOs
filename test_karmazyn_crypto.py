import sys
from unittest.mock import MagicMock

# Mocking dependencies that might be missing in the environment
mock_np = MagicMock()
sys.modules["numpy"] = mock_np
sys.modules["hss_karmazyn_matrix"] = MagicMock()
sys.modules["hss_demo"] = MagicMock()
# karmazyn.py imports N, Q from hss_demo
sys.modules["hss_demo"].N = 15
sys.modules["hss_demo"].Q = 256

import karmazyn

def test_xor_crypt_identity():
    """Verify that encrypting and then decrypting returns the original data."""
    data = b"Hello KarmazynOS, this is a test of the XOR crypt function."
    key = b"secret_key_123"
    encrypted = karmazyn._xor_crypt(data, key)
    decrypted = karmazyn._xor_crypt(encrypted, key)
    assert decrypted == data
    assert encrypted != data # Highly likely to be different

def test_xor_crypt_empty_data():
    """Verify that empty data returns empty output."""
    assert karmazyn._xor_crypt(b"", b"key") == b""

def test_xor_crypt_long_data():
    """Verify it works for data longer than one SHA256 block (32 bytes)."""
    data = bytes(range(256)) * 4 # 1024 bytes
    key = b"another_secret_key"
    encrypted = karmazyn._xor_crypt(data, key)
    assert len(encrypted) == len(data)
    assert karmazyn._xor_crypt(encrypted, key) == data

def test_xor_crypt_different_keys():
    """Verify that different keys produce different ciphertexts for the same data."""
    data = b"Same plaintext data"
    c1 = karmazyn._xor_crypt(data, b"key_a")
    c2 = karmazyn._xor_crypt(data, b"key_b")
    assert c1 != c2

def test_xor_crypt_consistency():
    """Verify that the same data and key always produce the same result."""
    data = b"Consistent data"
    key = b"consistent_key"
    assert karmazyn._xor_crypt(data, key) == karmazyn._xor_crypt(data, key)

def test_xor_crypt_block_boundaries():
    """Verify it handles block boundaries correctly."""
    key = b"boundary_test_key"
    for length in [31, 32, 33, 63, 64, 65]:
        data = b"A" * length
        encrypted = karmazyn._xor_crypt(data, key)
        assert len(encrypted) == length
        assert karmazyn._xor_crypt(encrypted, key) == data
