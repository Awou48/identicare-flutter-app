"""Staff identity: password hashing and short-lived JWTs.

Why this exists. Until now the only non-participant credential was ONE shared
static `X-Api-Key`. That is fatal for the two controls this release adds:

  * Four-eyes enrolment needs to know that the approver is a DIFFERENT person
    from the capturer. A shared key has no "who".
  * `STAFF_OVERRIDE_FREQUENCY` - the rule that actually catches a nurse who
    overrides twenty times a day - is meaningless without per-person identity.

No new dependencies: PyJWT arrives with firebase-admin, and scrypt is stdlib.
Deliberately NOT argon2 - adding a C-extension dependency on Windows for a
solo-maintained project is a cost with no benefit here, and scrypt with these
parameters is a sound password KDF.

The JWT signing key is derived from the KEK via HKDF, so there is exactly one
root secret to protect (backend/keys/kek.bin) rather than two.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.utils.errors import ApiError

# --------------------------------------------------------------------------- #
# Roles
# --------------------------------------------------------------------------- #
ROLE_PETUGAS = "petugas"
ROLE_SUPERVISOR = "supervisor"
ROLE_INVESTIGATOR = "investigator"
ROLE_ADMIN = "admin"

ROLES = (ROLE_PETUGAS, ROLE_SUPERVISOR, ROLE_INVESTIGATOR, ROLE_ADMIN)

# Who may act as whom. Deliberately NOT a simple ordering: an investigator reads
# fraud cases but must NOT be able to approve a clinical override, and a petugas
# must not read the investigator console. A flat hierarchy would quietly grant
# both.
ROLE_GRANTS: dict[str, frozenset[str]] = {
    ROLE_PETUGAS: frozenset({ROLE_PETUGAS}),
    ROLE_SUPERVISOR: frozenset({ROLE_PETUGAS, ROLE_SUPERVISOR}),
    ROLE_INVESTIGATOR: frozenset({ROLE_INVESTIGATOR}),
    ROLE_ADMIN: frozenset(ROLES),
}

TOKEN_TTL = timedelta(hours=8)  # one shift
JWT_ALGORITHM = "HS256"
HKDF_INFO = b"identicare-staff-jwt-v1"

# scrypt cost. n=2**15 keeps a single hash around 100 ms on a modern CPU, which
# is a sane brute-force cost for staff passwords without making login sluggish.
SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32


def _maxmem_for(n: int, r: int, p: int) -> int:
    """scrypt needs 128*n*r bytes, and OpenSSL refuses anything over a 32 MB
    default - so n=2**15, r=8 (33.5 MB) fails with "memory limit exceeded"
    unless maxmem is raised explicitly.

    Derived from the parameters rather than hardcoded, so the cost can be tuned
    later without also remembering to bump a magic number. Doubled for headroom.
    """
    return max(64 * 1024 * 1024, 128 * n * r * p * 2)


@dataclass(frozen=True)
class StaffPrincipal:
    staff_id: str
    nama: str
    role: str
    faskes_id: str | None

    def can_act_as(self, role: str) -> bool:
        return role in ROLE_GRANTS.get(self.role, frozenset())

    def require(self, role: str) -> None:
        if not self.can_act_as(role):
            raise ApiError(
                "FORBIDDEN",
                403,
                message=f"Aksi ini memerlukan peran {role}.",
                details={"your_role": self.role, "required_role": role},
            )


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    """scrypt with a random per-password salt. Returns a self-describing string
    so the cost parameters can be raised later without breaking old hashes."""
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
        maxmem=_maxmem_for(SCRYPT_N, SCRYPT_R, SCRYPT_P),
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time comparison. Returns False rather than raising on a
    malformed hash, so a corrupt record denies login instead of 500-ing."""
    try:
        scheme, n, r, p, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        n_i, r_i, p_i = int(n), int(r), int(p)
        candidate = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=n_i,
            r=r_i,
            p=p_i,
            dklen=len(bytes.fromhex(digest_hex)),
            # Read from the stored hash, so old hashes with different cost
            # parameters keep verifying after the constants above are raised.
            maxmem=_maxmem_for(n_i, r_i, p_i),
        )
        return hmac.compare_digest(candidate, bytes.fromhex(digest_hex))
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------------- #
# Tokens
# --------------------------------------------------------------------------- #
def _signing_key(kek: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=HKDF_INFO).derive(kek)


def issue_token(kek: bytes, *, staff_id: str, nama: str, role: str, faskes_id: str | None) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": staff_id,
        "nama": nama,
        "role": role,
        "faskes_id": faskes_id,
        "iat": int(now.timestamp()),
        "exp": int((now + TOKEN_TTL).timestamp()),
        # Distinguishes a staff token from any other HS256 token that might
        # reach this endpoint.
        "typ": "identicare-staff",
    }
    return jwt.encode(payload, _signing_key(kek), algorithm=JWT_ALGORITHM)


def verify_token(kek: bytes, token: str) -> StaffPrincipal:
    try:
        payload = jwt.decode(
            token,
            _signing_key(kek),
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise ApiError(
            "STAFF_TOKEN_EXPIRED", 401, message="Sesi petugas berakhir. Silakan login kembali."
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise ApiError("UNAUTHENTICATED", 401, message="Token petugas tidak valid.") from exc

    if payload.get("typ") != "identicare-staff":
        raise ApiError("UNAUTHENTICATED", 401, message="Token petugas tidak valid.")

    role = payload.get("role")
    if role not in ROLES:
        raise ApiError("UNAUTHENTICATED", 401, message="Peran petugas tidak dikenal.")

    return StaffPrincipal(
        staff_id=str(payload["sub"]),
        nama=payload.get("nama", ""),
        role=role,
        faskes_id=payload.get("faskes_id"),
    )
