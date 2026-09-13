from __future__ import annotations

from pathlib import Path

import numpy as np
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

ROTATION_ID = "rot-v1"
HKDF_INFO = b"identicare-rotation-v1"


def derive_rotation(kek: bytes, dim: int = 512) -> np.ndarray:
    """Deterministically derive a secret orthogonal matrix from the KEK."""
    seed_bytes = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=HKDF_INFO).derive(kek)
    seed = int.from_bytes(seed_bytes, "big") % (2**32)

    rng = np.random.default_rng(seed)
    gaussian = rng.standard_normal((dim, dim))
    q, r = np.linalg.qr(gaussian)
    q *= np.sign(np.diag(r))
    return np.ascontiguousarray(q, dtype=np.float64)


def save_rotation(matrix: np.ndarray, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, matrix)


def load_rotation(path: str | Path) -> np.ndarray:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Rotation matrix not found at {path}. Run: python scripts/gen_keys.py "
            "(it is derived from the KEK, so regenerating from the same KEK "
            "reproduces the identical matrix and existing search vectors stay valid)."
        )
    return np.load(path)


def apply_rotation(matrix: np.ndarray, vec: np.ndarray) -> np.ndarray:
    """Map a canonical-basis embedding into the secret basis."""
    return (matrix @ np.asarray(vec, dtype=np.float64)).astype(np.float32)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity. Invariant under a shared orthogonal rotation."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def l2_normalize(vec: np.ndarray) -> np.ndarray:
    vec = np.asarray(vec, dtype=np.float32)
    norm = float(np.linalg.norm(vec))
    if norm == 0.0:
        return vec
    return (vec / norm).astype(np.float32)
