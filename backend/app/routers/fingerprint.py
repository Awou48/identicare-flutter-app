"""Step 2 - Scan Sidik Jari.

The device's real fingerprint sensor gates access to a signing key; the server
verifies a signature over a server-issued nonce. What crosses the network is a
signature, never a boolean and never a fingerprint image - the biometric itself
never leaves the phone's secure hardware.
"""

from __future__ import annotations

import base64
import logging
import time
from datetime import UTC, datetime

from fastapi import APIRouter

from app import db as database
from app.deps import DbDep, RequestIdDep, SessionTokenDep, SettingsDep
from app.schemas.session import FingerprintStepResponse
from app.security import attestation, crypto
from app.security import nonce as nonce_service
from app.services import audit, session_service
from app.utils.errors import ApiError, message_for

log = logging.getLogger(__name__)
router = APIRouter(prefix="/verification/sessions", tags=["verification"])

MAX_FINGERPRINT_ATTEMPTS = 5
# Rejects a signature whose timestamp is implausible, which bounds how long a
# captured payload stays useful even before the nonce is consumed.
MAX_CLOCK_SKEW_SECONDS = 300


@router.post("/{session_id}/fingerprint", response_model=FingerprintStepResponse)
async def submit_fingerprint(
    session_id: str,
    payload: dict,
    db: DbDep,
    settings: SettingsDep,
    token: SessionTokenDep,
    request_id: RequestIdDep,
) -> FingerprintStepResponse:
    started = time.perf_counter()

    session = await session_service.load(db, session_id, token)
    await session_service.assert_live(db, session)
    session_service.require_state(session, "fingerprint")

    method = payload.get("method", attestation.METHOD_HMAC)
    if not attestation.method_is_supported(method):
        raise ApiError(
            "VALIDATION_ERROR",
            422,
            details={"method": method, "supported": sorted(attestation.SUPPORTED_METHODS)},
        )

    device_uid = payload.get("device_uid") or session["context"].get("device_uid")
    supplied_nonce = payload.get("nonce", "")
    signature_b64 = payload.get("signature_b64", "")
    timestamp = int(payload.get("timestamp") or 0)

    if not (device_uid and supplied_nonce and signature_b64):
        raise ApiError(
            "VALIDATION_ERROR", 422, details={"required": ["device_uid", "nonce", "signature_b64"]}
        )

    # Bind the signature to this device, this session, this participant and this
    # nonce. Any one of those missing lets a captured signature be replayed
    # somewhere it does not belong.
    canonical = attestation.canonical_payload(
        session_id=str(session["_id"]),
        nonce=supplied_nonce,
        device_uid=device_uid,
        no_bpjs=session["no_bpjs"],
        timestamp=timestamp,
    )

    skew = abs(int(datetime.now(UTC).timestamp()) - timestamp)
    if timestamp and skew > MAX_CLOCK_SKEW_SECONDS:
        return await _fail(
            db, session, "NONCE_EXPIRED", started, request_id,
            detail={"clock_skew_seconds": skew},
        )

    device = await db.devices.find_one({"device_uid": device_uid})
    if device is None:
        return await _fail(db, session, "DEVICE_NOT_ENROLLED", started, request_id)
    if device.get("blocked"):
        raise ApiError("DEVICE_BLOCKED", 423)

    try:
        signature = base64.b64decode(signature_b64)
    except Exception as exc:  # noqa: BLE001
        raise ApiError("VALIDATION_ERROR", 422, details={"field": "signature_b64"}) from exc

    # Consume the nonce BEFORE verifying. If verification ran first, an attacker
    # could probe signatures repeatedly against a still-valid nonce.
    nonce_error = await nonce_service.consume(db, supplied_nonce, session_id=session["_id"])
    if nonce_error:
        return await _fail(db, session, nonce_error, started, request_id)

    if method == attestation.METHOD_KEYSTORE:
        public_key = device.get("public_key_der")
        if not public_key:
            return await _fail(db, session, "KEY_MISMATCH", started, request_id)
        outcome = attestation.verify_ec_p256(
            payload=canonical, signature=signature, public_key_der=bytes(public_key)
        )
    else:
        secret_env = device.get("secret_enc")
        if not secret_env:
            return await _fail(db, session, "DEVICE_NOT_ENROLLED", started, request_id)
        kek = database.get_kek()
        aad = crypto.build_aad(device_uid, "device_secret", 1)
        try:
            secret = crypto.decrypt_blob(kek, secret_env, aad)
        except Exception:  # noqa: BLE001
            log.exception("device secret decrypt failed for %s", device_uid)
            return await _fail(db, session, "KEY_MISMATCH", started, request_id)
        outcome = attestation.verify_hmac(
            payload=canonical, signature=signature, shared_secret=secret
        )
        del secret

    if not outcome.ok:
        return await _fail(
            db, session, outcome.error_code or "SIGNATURE_INVALID", started, request_id
        )

    latency_ms = int((time.perf_counter() - started) * 1000)
    await session_service.advance(
        db,
        session,
        "fingerprint",
        {
            "method": method,
            "key_alias": payload.get("key_alias"),
            "security_level": outcome.security_level,
            "signature_verified": True,
            "nonce_consumed": supplied_nonce[:8] + "...",
            "device_uid": device_uid,
            "latency_ms": latency_ms,
        },
    )
    await audit.log_event(
        db,
        session_id=session["_id"],
        step="fingerprint",
        outcome="passed",
        peserta_id=session["peserta_id"],
        method=method,
        device_uid=device_uid,
        faskes_id=session["context"].get("faskes_id"),
        latency_ms=latency_ms,
        request_id=request_id,
    )

    message = "Verifikasi sidik jari berhasil."
    if outcome.security_level == "SOFTWARE":
        # Say so out loud rather than presenting Tier A as equivalent to hardware.
        message += " Catatan: perangkat belum terikat perangkat keras (TEE)."

    return FingerprintStepResponse(
        result="passed",
        signature_verified=True,
        security_level=outcome.security_level,
        user_auth_required=device.get("attestation", {}).get("user_auth_required"),
        next_step="review",
        message=message,
    )


async def _fail(
    db, session, code: str, started: float, request_id: str, detail: dict | None = None
) -> FingerprintStepResponse:
    latency_ms = int((time.perf_counter() - started) * 1000)
    _, attempts, exhausted = await session_service.record_failure(
        db,
        session,
        "fingerprint",
        {"error_code": code, "latency_ms": latency_ms, **(detail or {})},
        max_attempts=MAX_FINGERPRINT_ATTEMPTS,
    )
    await audit.log_event(
        db,
        session_id=session["_id"],
        step="fingerprint",
        outcome="failed",
        peserta_id=session["peserta_id"],
        error_code=code,
        device_uid=session["context"].get("device_uid"),
        latency_ms=latency_ms,
        request_id=request_id,
    )
    attempts_left = max(0, MAX_FINGERPRINT_ATTEMPTS - attempts)
    message = message_for(code)
    if exhausted:
        message += " Batas percobaan tercapai, sesi ditolak."

    return FingerprintStepResponse(
        result="failed",
        error_code="MAX_ATTEMPTS" if exhausted else code,
        message=message,
        signature_verified=False,
        attempts_used=attempts,
        attempts_left=attempts_left,
        next_step=None if exhausted else "fingerprint",
    )
