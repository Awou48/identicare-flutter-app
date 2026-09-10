"""Envelope encryption for biometric templates and NIK.

Design (see docs/SCHEMA.md 'Encrypting embeddings while still matching'):

  * Every secret blob gets its OWN random 256-bit DEK.
  * The DEK is sealed under a process-held KEK (backend/keys/kek.bin) and stored
    beside the ciphertext. The KEK never enters MongoDB, so a database dump alone
    is useless.
  * Both the payload and the wrapped DEK are AES-256-GCM with the SAME AAD string,
    which binds the ciphertext to the document that owns it. Moving Alice's sealed
    template onto Bob's record makes decryption fail authentication rather than
    silently succeed.

Nothing here is homomorphic. Matching happens on plaintext held in RAM for the
duration of one 1:1 comparison; the 1:N sweep uses rotation.py instead.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from pathlib import Path
from typing import Any

import numpy as np
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEK_BYTES = 32
DEK_BYTES = 32
NONCE_BYTES = 12


# --------------------------------------------------------------------------- #
# Key loading
# --------------------------------------------------------------------------- #
def generate_kek() -> bytes:
    return secrets.token_bytes(KEK_BYTES)


def load_kek(path: str | Path) -> bytes:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"KEK not found at {path}. Run: python scripts/gen_keys.py"
        )
    kek = path.read_bytes()
    if len(kek) != KEK_BYTES:
        raise ValueError(
            f"KEK at {path} is {len(kek)} bytes, expected {KEK_BYTES}. "
            "The file is corrupt — do NOT regenerate it if templates already exist, "
            "they would all become unreadable."
        )
    return kek


# --------------------------------------------------------------------------- #
# Envelope encryption
# --------------------------------------------------------------------------- #
def build_aad(peserta_id: Any, template_id: Any, version: int) -> str:
    """Canonical AAD. Binds a ciphertext to the document that owns it."""
    return f"{peserta_id}|{template_id}|v{version}"


def encrypt_blob(kek: bytes, plaintext: bytes, aad: str) -> dict[str, Any]:
    """Seal `plaintext` under a fresh DEK, itself wrapped by `kek`."""
    aad_bytes = aad.encode("utf-8")

    dek = secrets.token_bytes(DEK_BYTES)
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = AESGCM(dek).encrypt(nonce, plaintext, aad_bytes)

    dek_nonce = os.urandom(NONCE_BYTES)
    dek_wrapped = AESGCM(kek).encrypt(dek_nonce, dek, aad_bytes)

    return {
        "alg": "AES-256-GCM",
        "kek_id": "kek-v1",
        "dek_wrapped": dek_wrapped,
        "dek_nonce": dek_nonce,
        "nonce": nonce,
        "ciphertext": ciphertext,
        "aad": aad,
    }


def decrypt_blob(kek: bytes, env: dict[str, Any], aad: str) -> bytes:
    """Unwrap the DEK and decrypt. Raises InvalidTag if `aad` does not match."""
    aad_bytes = aad.encode("utf-8")
    dek = AESGCM(kek).decrypt(bytes(env["dek_nonce"]), bytes(env["dek_wrapped"]), aad_bytes)
    try:
        return AESGCM(dek).decrypt(bytes(env["nonce"]), bytes(env["ciphertext"]), aad_bytes)
    finally:
        del dek


# --------------------------------------------------------------------------- #
# Embedding (de)serialisation — float32 little-endian, 512 * 4 = 2048 bytes
# --------------------------------------------------------------------------- #
def pack_embedding(vec: np.ndarray) -> bytes:
    return np.ascontiguousarray(vec, dtype="<f4").tobytes()


def unpack_embedding(raw: bytes, dim: int = 512) -> np.ndarray:
    vec = np.frombuffer(raw, dtype="<f4")
    if vec.size != dim:
        raise ValueError(f"embedding has {vec.size} floats, expected {dim}")
    return vec.astype(np.float32, copy=True)


def encrypt_embedding(kek: bytes, vec: np.ndarray, aad: str) -> dict[str, Any]:
    return encrypt_blob(kek, pack_embedding(vec), aad)


def decrypt_embedding(kek: bytes, env: dict[str, Any], aad: str, dim: int = 512) -> np.ndarray:
    raw = decrypt_blob(kek, env, aad)
    return unpack_embedding(raw, dim)


def wipe(arr: np.ndarray) -> None:
    """Best-effort overwrite of a decrypted embedding buffer.

    CPython gives no guarantee the original bytes are gone (the GC may have moved
    them), but zeroing the array we control keeps the plaintext out of long-lived
    heap pages, which is the realistic threat here.
    """
    try:
        arr[:] = 0
    except (ValueError, TypeError):
        pass


# --------------------------------------------------------------------------- #
# NIK handling
# --------------------------------------------------------------------------- #
def hash_nik(nik: str, pepper: str) -> str:
    """Peppered SHA-256 for exact lookup.

    A bare SHA-256 of a NIK is worthless: the space is 16 digits with heavy
    structure (province/date encoded), so a dump would fall to offline brute force
    in seconds. The pepper lives in the environment, never in the database.
    """
    return hashlib.sha256(f"{pepper}{nik}".encode()).hexdigest()


def mask_nik(nik: str) -> str:
    """3271********7890 — first 4 and last 4 only."""
    if len(nik) <= 8:
        return "*" * len(nik)
    return f"{nik[:4]}{'*' * (len(nik) - 8)}{nik[-4:]}"


def mask_bpjs(no_bpjs: str) -> str:
    if len(no_bpjs) <= 6:
        return "*" * len(no_bpjs)
    return f"{no_bpjs[:3]}{'*' * (len(no_bpjs) - 6)}{no_bpjs[-3:]}"


def mask_name(nama: str) -> str:
    """Marcel Sebastian -> Marcel S********"""
    parts = nama.split()
    if len(parts) == 1:
        head = parts[0]
        return f"{head[:2]}{'*' * max(len(head) - 2, 0)}"
    tail = parts[-1]
    return f"{' '.join(parts[:-1])} {tail[0]}{'*' * max(len(tail) - 1, 0)}"


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
