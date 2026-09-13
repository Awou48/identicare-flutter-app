from __future__ import annotations

import hmac
import logging
from dataclasses import dataclass
from hashlib import sha256

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import load_der_public_key

log = logging.getLogger(__name__)

METHOD_HMAC = "hmac_sha256_shared_secret"
METHOD_KEYSTORE = "android_keystore_ec_p256"
SUPPORTED_METHODS = {METHOD_HMAC, METHOD_KEYSTORE}

PAYLOAD_PREFIX = "identicare-v1"


def canonical_payload(*, session_id: str, nonce: str, device_uid: str, no_bpjs: str, timestamp: int) -> str:
    """The exact bytes both sides sign."""
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
    except Exception as exc:
        return VerificationOutcome(False, "TEE", "KEY_MISMATCH", {"reason": str(exc)})

    if not isinstance(public_key, ec.EllipticCurvePublicKey):
        return VerificationOutcome(False, "TEE", "KEY_MISMATCH", {"reason": "bukan kunci EC"})

    try:
        public_key.verify(signature, payload.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        return VerificationOutcome(False, "TEE", "SIGNATURE_INVALID")
    except Exception as exc:
        return VerificationOutcome(False, "TEE", "SIGNATURE_INVALID", {"reason": str(exc)})

    return VerificationOutcome(True, "TEE")


KEY_DESCRIPTION_OID = "1.3.6.1.4.1.11129.2.1.17"

SECURITY_LEVELS = {0: "SOFTWARE", 1: "TEE", 2: "STRONGBOX"}
VERIFIED_BOOT_STATES = {0: "GREEN", 1: "YELLOW", 2: "ORANGE", 3: "RED"}


TAG_NO_AUTH_REQUIRED = 503
TAG_USER_AUTH_TYPE = 504
TAG_AUTH_TIMEOUT = 505
TAG_ROOT_OF_TRUST = 704
HW_AUTH_FINGERPRINT = 1 << 1


def _der_tlvs(buf: bytes):
    """Yield (tag_number, constructed, value) for each top-level DER element."""
    i, n = 0, len(buf)
    while i < n:
        first = buf[i]
        i += 1
        constructed = bool(first & 0x20)
        tag = first & 0x1F
        if tag == 0x1F:
            tag = 0
            while True:
                b = buf[i]
                i += 1
                tag = (tag << 7) | (b & 0x7F)
                if not b & 0x80:
                    break
        length = buf[i]
        i += 1
        if length & 0x80:
            count = length & 0x7F
            length = int.from_bytes(buf[i : i + count], "big")
            i += count
        yield tag, constructed, buf[i : i + length]
        i += length


def _authorization_list(seq: bytes) -> dict:
    """The parts of a Keymaster AuthorizationList that matter here."""
    out: dict = {"no_auth_required": False, "user_auth_type": None, "auth_timeout": None}
    for tag, _, value in _der_tlvs(seq):
        if tag == TAG_NO_AUTH_REQUIRED:
            out["no_auth_required"] = True
        elif tag == TAG_USER_AUTH_TYPE:
            inner = next(iter(_der_tlvs(value)), None)
            if inner:
                out["user_auth_type"] = int.from_bytes(inner[2], "big", signed=True)
        elif tag == TAG_AUTH_TIMEOUT:
            inner = next(iter(_der_tlvs(value)), None)
            if inner:
                out["auth_timeout"] = int.from_bytes(inner[2], "big", signed=True)
    return out


def parse_attestation(cert_der: bytes) -> dict:
    """Extract what the Android KeyDescription extension asserts."""
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
    except Exception as exc:
        result["error"] = f"cannot parse certificate: {exc}"
        return result

    try:
        ext = cert.extensions.get_extension_for_oid(x509.ObjectIdentifier(KEY_DESCRIPTION_OID))
    except x509.ExtensionNotFound:
        result["error"] = "no KeyDescription extension - not a hardware-attested key"
        return result

    try:
        outer = next(iter(_der_tlvs(ext.value.public_bytes())))
        if outer[0] != 0x10:
            raise ValueError("KeyDescription is not a SEQUENCE")
        fields = list(_der_tlvs(outer[2]))
        if len(fields) < 8:
            raise ValueError(f"KeyDescription has {len(fields)} fields, expected 8")
        level_idx = int.from_bytes(fields[1][2], "big")
        result["security_level"] = SECURITY_LEVELS.get(level_idx, "SOFTWARE")
        result["attestation_challenge"] = fields[4][2].hex()
        tee = _authorization_list(fields[7][2])
        result["tee_enforced"] = tee
        if tee["no_auth_required"]:
            result["user_auth_required"] = False
        elif tee["user_auth_type"] is not None:
            result["user_auth_required"] = bool(tee["user_auth_type"] & HW_AUTH_FINGERPRINT)
        result["parsed"] = True
    except Exception as exc:
        result["error"] = f"cannot decode KeyDescription: {exc}"
    return result


def evaluate_attestation_chain(
    chain_der: list[bytes], *, public_key_der: bytes, expected_challenge: bytes
) -> dict:
    """What the device's key attestation says about the key we were handed."""
    out: dict = {
        "chain_verified": False,
        "parsed": False,
        "key_matches": False,
        "challenge_ok": False,
        "security_level": "SOFTWARE",
        "chain_length": len(chain_der),
    }
    if not chain_der:
        out["error"] = "no chain"
        return out

    leaf = parse_attestation(chain_der[0])
    out.update(
        {k: leaf.get(k) for k in ("parsed", "security_level", "attestation_challenge", "user_auth_required")}
    )
    if leaf.get("error"):
        out["error"] = leaf["error"]

    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization

        cert = x509.load_der_x509_certificate(chain_der[0])
        leaf_spki = cert.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        out["key_matches"] = leaf_spki == public_key_der
    except Exception as exc:
        out["error"] = f"cannot read leaf public key: {exc}"

    if leaf.get("attestation_challenge") is not None:
        out["challenge_ok"] = leaf["attestation_challenge"] == expected_challenge.hex()

    if not (out["parsed"] and out["key_matches"] and out["challenge_ok"]):
        out["security_level"] = "SOFTWARE"
    return out


def method_is_supported(method: str) -> bool:
    return method in SUPPORTED_METHODS
