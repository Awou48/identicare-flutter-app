from __future__ import annotations

import numpy as np
import pytest

from app.security import crypto, rotation

DIM = 512
TOL = 1e-6


@pytest.fixture(scope="module")
def kek() -> bytes:
    return crypto.generate_kek()


@pytest.fixture(scope="module")
def matrix(kek: bytes) -> np.ndarray:
    return rotation.derive_rotation(kek, dim=DIM)


def test_matrix_is_orthogonal(matrix: np.ndarray) -> None:
    identity = matrix @ matrix.T
    assert np.abs(identity - np.eye(DIM)).max() < 1e-9


def test_determinant_is_unit(matrix: np.ndarray) -> None:
    assert abs(abs(float(np.linalg.det(matrix))) - 1.0) < 1e-9


def test_derivation_is_deterministic(kek: bytes) -> None:
    """Same KEK must give the same R, or every stored search_vector is orphaned."""
    a = rotation.derive_rotation(kek, dim=64)
    b = rotation.derive_rotation(kek, dim=64)
    np.testing.assert_array_equal(a, b)


def test_different_kek_gives_different_rotation() -> None:
    a = rotation.derive_rotation(crypto.generate_kek(), dim=64)
    b = rotation.derive_rotation(crypto.generate_kek(), dim=64)
    assert not np.allclose(a, b)


def test_cosine_is_preserved_exactly(matrix: np.ndarray) -> None:
    """The load-bearing property."""
    rng = np.random.default_rng(42)
    for _ in range(200):
        x = rng.standard_normal(DIM).astype(np.float32)
        y = rng.standard_normal(DIM).astype(np.float32)

        plain = rotation.cosine(x, y)
        rotated = rotation.cosine(rotation.apply_rotation(matrix, x), rotation.apply_rotation(matrix, y))
        assert abs(plain - rotated) < TOL, f"drift {abs(plain - rotated):.2e}"


def test_cosine_preserved_for_normalized_vectors(matrix: np.ndarray) -> None:
    """ArcFace embeddings are L2-normalized, so test that case specifically."""
    rng = np.random.default_rng(1234)
    for _ in range(200):
        x = rotation.l2_normalize(rng.standard_normal(DIM))
        y = rotation.l2_normalize(rng.standard_normal(DIM))
        assert (
            abs(
                rotation.cosine(x, y)
                - rotation.cosine(rotation.apply_rotation(matrix, x), rotation.apply_rotation(matrix, y))
            )
            < TOL
        )


def test_norm_is_preserved(matrix: np.ndarray) -> None:
    rng = np.random.default_rng(9)
    x = rng.standard_normal(DIM)
    assert abs(float(np.linalg.norm(rotation.apply_rotation(matrix, x))) - float(np.linalg.norm(x))) < 1e-4


def test_self_similarity_is_one(matrix: np.ndarray) -> None:
    x = rotation.l2_normalize(np.random.default_rng(3).standard_normal(DIM))
    rx = rotation.apply_rotation(matrix, x)
    assert abs(rotation.cosine(rx, rx) - 1.0) < TOL


def test_a_match_still_reads_as_a_match_after_rotation(matrix: np.ndarray) -> None:
    """End-to-end: two noisy captures of the same identity must clear the 0.42 accept threshold in the rotated
    basis exactly as they do in the plain one.
    """
    rng = np.random.default_rng(2026)
    enrolled = rotation.l2_normalize(rng.standard_normal(DIM))
    probe = rotation.l2_normalize(enrolled + 0.05 * rng.standard_normal(DIM))

    plain = rotation.cosine(enrolled, probe)
    rotated = rotation.cosine(
        rotation.apply_rotation(matrix, enrolled), rotation.apply_rotation(matrix, probe)
    )

    assert plain > 0.42, "fixture is not a match; adjust the noise level"
    assert abs(plain - rotated) < TOL


def test_rotated_vector_is_not_the_original(matrix: np.ndarray) -> None:
    """A dump of search_vector must not hand an attacker the canonical embedding."""
    x = rotation.l2_normalize(np.random.default_rng(11).standard_normal(DIM))
    rotated = rotation.apply_rotation(matrix, x)
    assert not np.allclose(x, rotated, atol=1e-3)
    assert not np.allclose(np.sort(x), np.sort(rotated), atol=1e-3)


def test_cross_basis_comparison_is_meaningless(matrix: np.ndarray) -> None:
    """Comparing a rotated vector against a canonical one gives noise, which is exactly why a leaked dump
    cannot be matched against a public ArcFace gallery.
    """
    rng = np.random.default_rng(77)
    x = rotation.l2_normalize(rng.standard_normal(DIM))
    mixed = rotation.cosine(x, rotation.apply_rotation(matrix, x))
    assert abs(mixed) < 0.3, "rotation failed to decorrelate the basis"


def test_end_to_end_encrypt_rotate_decrypt(kek: bytes, matrix: np.ndarray) -> None:
    """The exact path seed_peserta.py and /enrollment/face take."""
    rng = np.random.default_rng(5150)
    vec = rotation.l2_normalize(rng.standard_normal(DIM))

    aad = crypto.build_aad("peserta123", "template456", 1)
    env = crypto.encrypt_embedding(kek, vec, aad)
    search_vector = rotation.apply_rotation(matrix, vec)

    recovered = crypto.decrypt_embedding(kek, env, aad, dim=DIM)
    np.testing.assert_array_equal(vec, recovered)

    probe = rotation.l2_normalize(vec + 0.05 * rng.standard_normal(DIM))
    assert (
        abs(
            rotation.cosine(recovered, probe)
            - rotation.cosine(search_vector, rotation.apply_rotation(matrix, probe))
        )
        < TOL
    )

    crypto.wipe(recovered)
    assert not recovered.any()


def test_rotation_load_missing_points_at_the_fix(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="gen_keys.py"):
        rotation.load_rotation(tmp_path / "nope.npy")


def test_save_load_roundtrip(matrix: np.ndarray, tmp_path) -> None:
    path = tmp_path / "rot.npy"
    rotation.save_rotation(matrix, path)
    np.testing.assert_array_equal(matrix, rotation.load_rotation(path))
