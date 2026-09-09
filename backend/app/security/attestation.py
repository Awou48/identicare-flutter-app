"""Fingerprint step verification.

`local_auth` on its own returns a BOOLEAN. A boolean crossing a network is not a
second factor - a rooted device or a patched APK returns true for free, and the
server has no way to tell. The signature has to come from hardware the app
cannot lie about.

Two tiers, both speaking the same API contract via the `method` field:

  Tier A  hmac_sha256_shared_secret
          local_auth gates the UX, then the app signs the canonical payload with
          a 32-byte secret held in flutter_secure_storage (itself Keystore-backed).
          Recorded as security_level "SOFTWARE", which fires the
          SOFTWARE_KEY_ONLY fraud signal. Be honest about what this is: a shared
          secret with no hardware binding. If an attacker extracts it, they can
          forge signatures. It ships first so the flow is end-to-end green.

  Tier B  android_keystore_ec_p256
          An EC P-256 key generated INSIDE the TEE with
          setUserAuthenticationRequired(true), so Android releases it for signing
          only after the fingerprint sensor authenticates - enforced by the TEE,
          not by app code. The private key is non-exportable. Recorded as "TEE".

The canonical payload is identical for both, so Tier B is a drop-in upgrade.
"""

from __future__ import annotations

import hmac
import logging
from dataclasses import dataclass
from hashlib import sha256

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import Prehashed  # noqa: F401
from cryptography.hazmat.primitives.serialization import load_der_public_key

log = logging.getLogger(__name__)

METHOD_HMAC = "hmac_sha256_shared_secret"
METHOD_KEYSTORE = "android_keystore_ec_p256"
SUPPORTED_METHODS = {METHOD_HMAC, METHOD_KEYSTORE}

PAYLOAD_PREFIX = "identicare-v1"


def canonical_payload(
    *, session_id: str, nonce: str, device_uid: str, no_bpjs: str, timestamp: int
) -> str:
    """The exact bytes both sides sign.

    Every field is bound in on purpose: session_id stops a signature being
    replayed onto a different claim, nonce stops replay onto the same one,
    device_uid binds it to the enrolled device, and no_bpjs stops it being
    applied to another participant.
    """
    return f"{PAYLOAD_PREFIX}|{session_id}|{nonce}|{device_uid}|{no_bpjs}|{timestamp}"


@dataclass
class VerificationOutcome:
    ok: bool
    security_level: str
    error_code: str | None = None
    detail: dict | None = None


def verify_hmac(*, payload: str, signature: bytes, shared_secret: bytes) -> VerificationOutcome:
    expected = hmac.new(shared_secret, payload.encode("utf-8"), sha256).digest()
    if hmac.compare_digest(expected, signature):
        return VerificationOutcome(True, "SOFTWARE")
    return VerificationOutcome(False, "SOFTWARE", "SIGNATURE_INVALID")


def verify_ec_p256(*, payload: str, signature: bytes, public_key_der: bytes) -> VerificationOutcome:
    try:
        public_key = load_der_public_key(public_key_der)
    except Exception as exc:  # noqa: BLE001
        return VerificationOutcome(False, "TEE", "KEY_MISMATCH", {"reason": str(exc)})

    if not isinstance(public_key, ec.EllipticCurvePublicKey):
        return VerificationOutcome(False, "TEE", "KEY_MISMATCH", {"reason": "bukan kunci EC"})

    try:
        public_key.verify(signature, payload.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        return VerificationOutcome(False, "TEE", "SIGNATURE_INVALID")
    except Exception as exc:  # noqa: BLE001
        return VerificationOutcome(False, "TEE", "SIGNATURE_INVALID", {"reason": str(exc)})

    return VerificationOutcome(True, "TEE")


# --------------------------------------------------------------------------- #
# Android key attestation certificate chain
# --------------------------------------------------------------------------- #
KEY_DESCRIPTION_OID = "1.3.6.1.4.1.11129.2.1.17"

SECURITY_LEVELS = {0: "SOFTWARE", 1: "TEE", 2: "STRONGBOX"}
VERIFIED_BOOT_STATES = {0: "GREEN", 1: "YELLOW", 2: "ORANGE", 3: "RED"}


def parse_attestation(cert_der: bytes) -> dict:
    """Extract what the Android KeyDescription extension asserts.

    Full chain validation to the pinned Google Hardware Attestation Root is a
    Tier B hardening task; this parses the claims so they can be recorded and
    surfaced now. Until the chain is validated the values are ASSERTED BY THE
    DEVICE, not proven - `chain_verified` stays false and callers must treat it
    that way rather than trusting the security_level blindly.
    """
    from cryptography import x509

    result: dict = {
        "chain_verified": False,
        "security_level": "SOFTWARE",
        "verified_boot": None,
        "user_auth_required": None,
        "attestation_challenge": None,
        "parsed": False,
    }
    try:
        cert = x509.load_der_x509_certificate(cert_der)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"cannot parse certificate: {exc}"
        return result

    try:
        ext = cert.extensions.get_extension_for_oid(x509.ObjectIdentifier(KEY_DESCRIPTION_OID))
    except x509.ExtensionNotFound:
        result["error"] = "no KeyDescription extension - not a hardware-attested key"
        return result

    try:
        from pyasn1.codec.der.decoder import decode as der_decode

        decoded, _ = der_decode(ext.value.public_bytes())
        # KeyDescription ::= SEQUENCE {
        #   attestationVersion, attestationSecurityLevel, keymasterVersion,
        #   keymasterSecurityLevel, attestationChallenge, uniqueId,
        #   softwareEnforced, teeEnforced }
        level_idx = int(decoded[1])
        result["security_level"] = SECURITY_LEVELS.get(level_idx, "SOFTWARE")
        result["attestation_challenge"] = bytes(decoded[4]).hex()
        result["parsed"] = True
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"cannot decode KeyDescription: {exc}"
    return result


def method_is_supported(method: str) -> bool:
    return method in SUPPORTED_METHODS
