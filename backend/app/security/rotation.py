"""Secret orthogonal rotation for the 1:N biometric search index.

The problem: AES-GCM ciphertext cannot be compared. AES is not homomorphic, and a
real homomorphic scheme (CKKS/SEAL) is a multi-week build at roughly 100x the
latency. But the fraud engine has to answer "does this face already exist under a
different no_bpjs?" across every enrolled peserta, and decrypting the whole
collection to do it would defeat the point of encrypting it.

The resolution: store R.v alongside the ciphertext, where R is a fixed secret
512x512 orthogonal matrix that never touches MongoDB.

    (Rx).(Ry) = x^T R^T R y = x^T y        because R^T R = I
    ||Rx||    = ||x||

so cosine(Rx, Ry) == cosine(x, y) exactly, to float precision. The sweep runs on
rotated vectors with ZERO decryptions and identical scores, and it ports unchanged
to Atlas $vectorSearch later.

Honest limits — state these, do not oversell them:

  * This is distance-preserving PSEUDONYMISATION, not semantic security. An
    adversary holding 512 or more (plaintext, rotated) pairs recovers R by least
    squares. An adversary holding R plus a dump recovers every template.
  * What it does buy: a stolen dump yields vectors in a basis no public ArcFace
    tool, no published embedding-inversion model, and no other leaked biometric
    database can consume. That is a real and useful property, and it is the same
    trick production FRT systems use for their search tier.
  * Therefore R lives only in keys/, never in the database or its backups;
    plaintext embeddings and enrolment images are never persisted anywhere; R is
    regenerated whenever the model version changes; and the AES-GCM blob, not the
    search vector, remains the record of truth for the accept/reject decision.

R is derived deterministically from the KEK via HKDF, so it is regenerable from a
KEK backup — losing rotation_v1.npy alone is recoverable, losing the KEK is not.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

ROTATION_ID = "rot-v1"
HKDF_INFO = b"identicare-rotation-v1"


def derive_rotation(kek: bytes, dim: int = 512) -> np.ndarray:
    """Deterministically derive a secret orthogonal matrix from the KEK.

    QR of a Gaussian matrix gives a Haar-uniform orthogonal Q. The diagonal sign
    correction is what makes numpy's QR output canonical — without it the same
    seed can yield sign-flipped columns across LAPACK versions, which would
    silently invalidate every stored search_vector.
    """
    seed_bytes = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=HKDF_INFO
    ).derive(kek)
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
