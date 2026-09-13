from __future__ import annotations

import numpy as np
import pytest
from cryptography.exceptions import InvalidTag

from app.security import crypto


@pytest.fixture
def kek() -> bytes:
    return crypto.generate_kek()


def test_blob_roundtrip(kek: bytes) -> None:
    aad = crypto.build_aad("peserta1", "tmpl1", 1)
    env = crypto.encrypt_blob(kek, b"3174050412010001", aad)
    assert crypto.decrypt_blob(kek, env, aad) == b"3174050412010001"


def test_ciphertext_is_not_plaintext(kek: bytes) -> None:
    nik = b"3174050412010001"
    env = crypto.encrypt_blob(kek, nik, crypto.build_aad("p", "t", 1))
    assert nik not in env["ciphertext"]
    assert len(env["nonce"]) == crypto.NONCE_BYTES
    assert len(env["ciphertext"]) == len(nik) + 16


def test_same_plaintext_encrypts_differently(kek: bytes) -> None:
    """Fresh DEK and nonce each time, so identical NIKs are not linkable in a dump."""
    aad = crypto.build_aad("p", "t", 1)
    a = crypto.encrypt_blob(kek, b"same", aad)
    b = crypto.encrypt_blob(kek, b"same", aad)
    assert a["ciphertext"] != b["ciphertext"]
    assert a["dek_wrapped"] != b["dek_wrapped"]


def test_wrong_kek_fails(kek: bytes) -> None:
    aad = crypto.build_aad("p", "t", 1)
    env = crypto.encrypt_blob(kek, b"secret", aad)
    with pytest.raises(InvalidTag):
        crypto.decrypt_blob(crypto.generate_kek(), env, aad)


def test_aad_binds_ciphertext_to_its_document(kek: bytes) -> None:
    """The point of the AAD: an attacker with Mongo write access cannot move Alice's sealed template onto
    Bob's record and have it decrypt.
    """
    alice_aad = crypto.build_aad("alice", "tmpl_a", 1)
    bob_aad = crypto.build_aad("bob", "tmpl_b", 1)

    env = crypto.encrypt_blob(kek, b"alice-biometric", alice_aad)
    assert crypto.decrypt_blob(kek, env, alice_aad) == b"alice-biometric"

    with pytest.raises(InvalidTag):
        crypto.decrypt_blob(kek, env, bob_aad)


def test_version_bump_invalidates_aad(kek: bytes) -> None:
    env = crypto.encrypt_blob(kek, b"x", crypto.build_aad("p", "t", 1))
    with pytest.raises(InvalidTag):
        crypto.decrypt_blob(kek, env, crypto.build_aad("p", "t", 2))


def test_tampered_ciphertext_is_rejected(kek: bytes) -> None:
    aad = crypto.build_aad("p", "t", 1)
    env = crypto.encrypt_blob(kek, b"0123456789abcdef", aad)
    tampered = bytearray(env["ciphertext"])
    tampered[0] ^= 0x01
    env["ciphertext"] = bytes(tampered)
    with pytest.raises(InvalidTag):
        crypto.decrypt_blob(kek, env, aad)


def test_embedding_roundtrip_is_exact(kek: bytes) -> None:
    rng = np.random.default_rng(7)
    vec = rng.standard_normal(512).astype(np.float32)
    aad = crypto.build_aad("p", "t", 1)

    env = crypto.encrypt_embedding(kek, vec, aad)
    out = crypto.decrypt_embedding(kek, env, aad, dim=512)

    np.testing.assert_array_equal(vec, out)


def test_embedding_ciphertext_size(kek: bytes) -> None:
    vec = np.zeros(512, dtype=np.float32)
    env = crypto.encrypt_embedding(kek, vec, crypto.build_aad("p", "t", 1))
    assert len(env["ciphertext"]) == 512 * 4 + 16


def test_unpack_rejects_wrong_dimension() -> None:
    with pytest.raises(ValueError, match="expected 512"):
        crypto.unpack_embedding(np.zeros(128, dtype="<f4").tobytes(), dim=512)


def test_wipe_zeroes_the_buffer() -> None:
    vec = np.ones(512, dtype=np.float32)
    crypto.wipe(vec)
    assert not vec.any()


def test_hash_nik_is_deterministic_and_peppered() -> None:
    nik = "3174050412010001"
    assert crypto.hash_nik(nik, "pepper") == crypto.hash_nik(nik, "pepper")
    assert crypto.hash_nik(nik, "pepper") != crypto.hash_nik(nik, "other-pepper")
    assert len(crypto.hash_nik(nik, "pepper")) == 64


def test_masking() -> None:
    assert crypto.mask_nik("3174050412010001") == "3174********0001"
    assert crypto.mask_bpjs("0001234567890") == "000*******890"
    assert crypto.mask_name("Marcel Sebastian") == "Marcel S********"
    assert crypto.mask_name("Marcel") == "Ma****"


def test_load_kek_rejects_wrong_length(tmp_path) -> None:
    bad = tmp_path / "kek.bin"
    bad.write_bytes(b"too-short")
    with pytest.raises(ValueError, match="expected 32"):
        crypto.load_kek(bad)


def test_load_kek_missing_points_at_the_fix(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="gen_keys.py"):
        crypto.load_kek(tmp_path / "nope.bin")
