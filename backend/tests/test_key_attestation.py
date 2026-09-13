from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from app.security import attestation

CHALLENGE = b"device-uid-0123456789abcdef"


def _len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    body = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(body)]) + body


def _tlv(tag: bytes, value: bytes) -> bytes:
    return tag + _len(len(value)) + value


def _int(tag: int, v: int) -> bytes:
    return _tlv(bytes([tag]), v.to_bytes(max(1, (v.bit_length() + 8) // 8), "big", signed=True))


def _ctx(tag_no: int, inner: bytes) -> bytes:
    """Context-specific, constructed (EXPLICIT) tag with a high tag number."""
    assert tag_no >= 31
    parts = []
    while tag_no:
        parts.append(tag_no & 0x7F)
        tag_no >>= 7
    parts.reverse()
    head = bytes([0xBF] + [b | 0x80 for b in parts[:-1]] + [parts[-1]])
    return _tlv(head, inner)


def _authorization_list(*, no_auth_required: bool, user_auth_type: int | None) -> bytes:
    items = b""
    if no_auth_required:
        items += _ctx(attestation.TAG_NO_AUTH_REQUIRED, bytes([0x05, 0x00]))
    if user_auth_type is not None:
        items += _ctx(attestation.TAG_USER_AUTH_TYPE, _int(0x02, user_auth_type))
    return _tlv(bytes([0x30]), items)


def _key_description(
    level: int, challenge: bytes, *, no_auth_required: bool = False, user_auth_type: int | None = 2
) -> bytes:
    body = (
        _int(0x02, 200)
        + _int(0x0A, level)
        + _int(0x02, 200)
        + _int(0x0A, level)
        + _tlv(bytes([0x04]), challenge)
        + _tlv(bytes([0x04]), b"")
        + _tlv(bytes([0x30]), b"")
        + _authorization_list(no_auth_required=no_auth_required, user_auth_type=user_auth_type)
    )
    return _tlv(bytes([0x30]), body)


def _chain(device_key: ec.EllipticCurvePrivateKey, *, level: int, challenge: bytes, **auth) -> list[bytes]:
    """[leaf over device_key signed by a fake attestation CA, the CA]."""
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Fake Android Keystore CA")])
    now = datetime.now(UTC)
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(1)
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .sign(ca_key, hashes.SHA256())
    )
    leaf = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Android Keystore Key")]))
        .issuer_name(ca_name)
        .public_key(device_key.public_key())
        .serial_number(2)
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(
            x509.UnrecognizedExtension(
                x509.ObjectIdentifier(attestation.KEY_DESCRIPTION_OID),
                _key_description(level, challenge, **auth),
            ),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    return [leaf.public_bytes(serialization.Encoding.DER), ca.public_bytes(serialization.Encoding.DER)]


def _spki(key: ec.EllipticCurvePrivateKey) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def test_tee_chain_over_the_right_key_and_challenge_is_hardware() -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    out = attestation.evaluate_attestation_chain(
        _chain(key, level=1, challenge=CHALLENGE), public_key_der=_spki(key), expected_challenge=CHALLENGE
    )
    assert out["parsed"] and out["key_matches"] and out["challenge_ok"]
    assert out["security_level"] == "TEE"
    assert out["user_auth_required"] is True
    assert out["chain_verified"] is False


def test_strongbox_is_recognised() -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    out = attestation.evaluate_attestation_chain(
        _chain(key, level=2, challenge=CHALLENGE), public_key_der=_spki(key), expected_challenge=CHALLENGE
    )
    assert out["security_level"] == "STRONGBOX"


def test_chain_for_a_different_key_earns_nothing() -> None:
    """The attack: a genuine TEE chain from some other key, sent alongside a software key the attacker
    controls. The level must not transfer.
    """
    real, attacker = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    out = attestation.evaluate_attestation_chain(
        _chain(real, level=1, challenge=CHALLENGE),
        public_key_der=_spki(attacker),
        expected_challenge=CHALLENGE,
    )
    assert out["parsed"] and not out["key_matches"]
    assert out["security_level"] == "SOFTWARE"


def test_chain_minted_for_another_device_earns_nothing() -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    out = attestation.evaluate_attestation_chain(
        _chain(key, level=1, challenge=b"some-other-device"),
        public_key_der=_spki(key),
        expected_challenge=CHALLENGE,
    )
    assert out["key_matches"] and not out["challenge_ok"]
    assert out["security_level"] == "SOFTWARE"


def test_software_keymaster_stays_software() -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    out = attestation.evaluate_attestation_chain(
        _chain(key, level=0, challenge=CHALLENGE), public_key_der=_spki(key), expected_challenge=CHALLENGE
    )
    assert out["security_level"] == "SOFTWARE"


def test_no_chain_is_software_not_an_error() -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    out = attestation.evaluate_attestation_chain([], public_key_der=_spki(key), expected_challenge=CHALLENGE)
    assert out["security_level"] == "SOFTWARE" and out["chain_length"] == 0


def test_signature_made_by_the_attested_key_verifies() -> None:
    """End to end on the crypto: the key the chain certifies signs the canonical payload the way
    SHA256withECDSA on Android does (DER signature), and the server verifies it against the enrolled SPKI.
    """
    key = ec.generate_private_key(ec.SECP256R1())
    payload = attestation.canonical_payload(
        session_id="s", nonce="n", device_uid="d", no_bpjs="0001234567890", timestamp=1
    )
    sig = key.sign(payload.encode(), ec.ECDSA(hashes.SHA256()))
    assert attestation.verify_ec_p256(payload=payload, signature=sig, public_key_der=_spki(key)).ok
    assert not attestation.verify_ec_p256(payload=payload + "x", signature=sig, public_key_der=_spki(key)).ok


def test_user_auth_requirement_is_read_from_the_certificate() -> None:
    """The app says it set setUserAuthenticationRequired(true). The server does not take its word: the TEE-
    enforced AuthorizationList either carries noAuthRequired (tag 503) or a userAuthType (tag 504) with the
    fingerprint bit, and that is what decides.
    """
    key = ec.generate_private_key(ec.SECP256R1())
    spki = _spki(key)

    no_auth = _chain(key, level=1, challenge=CHALLENGE, no_auth_required=True, user_auth_type=None)
    out = attestation.evaluate_attestation_chain(no_auth, public_key_der=spki, expected_challenge=CHALLENGE)
    assert out["user_auth_required"] is False

    password_only = _chain(key, level=1, challenge=CHALLENGE, user_auth_type=1)
    out = attestation.evaluate_attestation_chain(
        password_only, public_key_der=spki, expected_challenge=CHALLENGE
    )
    assert out["user_auth_required"] is False

    fingerprint = _chain(key, level=1, challenge=CHALLENGE, user_auth_type=2)
    out = attestation.evaluate_attestation_chain(
        fingerprint, public_key_der=spki, expected_challenge=CHALLENGE
    )
    assert out["user_auth_required"] is True
