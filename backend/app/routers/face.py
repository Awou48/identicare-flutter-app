"""Step 1 - Scan Wajah.

Transport is multipart, not base64 JSON. Base64 inflates every JPEG by 33% (on a
3-frame burst that is roughly 120 KB of extra Wi-Fi per attempt), forces an extra
encode/decode pass on both ends, and makes the server buffer the whole request as
a Python string before parsing. UploadFile streams.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, File, Form, UploadFile
from starlette.concurrency import run_in_threadpool

from app import db as database
from app.deps import DbDep, RequestIdDep, SessionTokenDep, SettingsDep
from app.schemas.session import FaceQuality, FaceStepResponse, LivenessChallenge, LivenessInfo
from app.security import nonce as nonce_service
from app.services import audit, face_engine, liveness, matcher, session_service
from app.services.face_engine import FrameAnalysis
from app.utils import images
from app.utils.errors import ApiError, message_for

log = logging.getLogger(__name__)
router = APIRouter(prefix="/verification/sessions", tags=["verification"])

CHALLENGE_TTL_SECONDS = 120


@router.post("/{session_id}/liveness/challenge", response_model=LivenessChallenge)
async def issue_challenge(
    session_id: str, db: DbDep, token: SessionTokenDep
) -> LivenessChallenge:
    """Issue a random, single-use liveness challenge.

    This is what actually defeats replay. The direction is chosen server-side
    AFTER the client asks, so a pre-recorded video cannot already satisfy it.
    """
    session = await session_service.load(db, session_id, token)
    await session_service.assert_live(db, session)
    session_service.require_state(session, "face")

    # SECURITY: if a live challenge already exists, return THAT one. Minting a
    # fresh random challenge on every call would let an attacker holding a
    # pre-recorded "turn left" video simply re-request until the server happened
    # to ask for turn_left - which defeats the entire point of the challenge.
    existing = session.get("steps", {}).get("face", {})
    prior_expiry = existing.get("challenge_expires_at")
    if prior_expiry is not None and prior_expiry.tzinfo is None:
        prior_expiry = prior_expiry.replace(tzinfo=UTC)
    if existing.get("challenge") and prior_expiry and datetime.now(UTC) < prior_expiry:
        return LivenessChallenge(
            challenge_id=existing["challenge_id"],
            challenge=existing["challenge"],
            instruction=liveness.CHALLENGE_TEXT[existing["challenge"]],
            expires_at=prior_expiry,
        )

    challenge = liveness.new_challenge()
    challenge_id = f"c_{session_service.new_nonce()[:12]}"
    expires = datetime.now(UTC) + timedelta(seconds=CHALLENGE_TTL_SECONDS)

    await db.verification_sessions.update_one(
        {"_id": session["_id"]},
        {
            "$set": {
                "steps.face.challenge_id": challenge_id,
                "steps.face.challenge": challenge,
                "steps.face.challenge_expires_at": expires,
            }
        },
    )
    return LivenessChallenge(
        challenge_id=challenge_id,
        challenge=challenge,
        instruction=liveness.CHALLENGE_TEXT[challenge],
        expires_at=expires,
    )


@router.post("/{session_id}/face", response_model=FaceStepResponse)
async def submit_face(
    session_id: str,
    db: DbDep,
    settings: SettingsDep,
    token: SessionTokenDep,
    request_id: RequestIdDep,
    frames: list[UploadFile] = File(...),
    meta: str = Form("{}"),
) -> FaceStepResponse:
    started = time.perf_counter()

    session = await session_service.load(db, session_id, token)
    await session_service.assert_live(db, session)
    session_service.require_state(session, "face")

    engine = face_engine.get_engine()
    if engine is None:
        raise ApiError("MODEL_UNAVAILABLE", 503, details={"reason": face_engine.load_error()})

    if not frames:
        raise ApiError("NO_FRAMES", 400)

    try:
        meta_obj = json.loads(meta) if meta else {}
    except json.JSONDecodeError:
        meta_obj = {}

    payloads = []
    for upload in frames:
        raw = await upload.read()
        if len(raw) > images.MAX_BYTES:
            raise ApiError("IMAGE_TOO_LARGE", 413, details={"bytes": len(raw)})
        payloads.append(raw)

    template = await matcher.get_active_template(db, session["peserta_id"])
    if template is None:
        raise ApiError("BIOMETRIC_NOT_ENROLLED", 409)

    challenge = session.get("steps", {}).get("face", {}).get("challenge")

    # All CPU-bound work happens in one worker-thread hop so the event loop stays
    # responsive while ONNX runs.
    analyses, probe, live_result = await run_in_threadpool(
        _analyse, engine, payloads, challenge, settings.liveness_min_score
    )

    quality = _quality_of(analyses)
    failure = _first_failure(analyses)

    if failure is not None or probe is None:
        return await _fail(
            db,
            session,
            settings,
            code=failure or "NO_FACE_DETECTED",
            quality=quality,
            liveness_info=_liveness_info(live_result),
            started=started,
            request_id=request_id,
        )

    if live_result is not None and not live_result.passed:
        return await _fail(
            db,
            session,
            settings,
            code="LIVENESS_FAILED",
            quality=quality,
            liveness_info=_liveness_info(live_result),
            started=started,
            request_id=request_id,
            extra={"liveness_score": live_result.score},
        )

    kek = database.get_kek()
    score = await matcher.match_one(
        db,
        kek,
        template,
        probe,
        actor=session["context"].get("firebase_uid", "unknown"),
        session_id=session["_id"],
        dim=settings.face_embedding_dim,
    )
    verdict = matcher.decide(score, settings.face_match_accept, settings.face_match_review)

    if verdict == "reject":
        return await _fail(
            db,
            session,
            settings,
            code="FACE_MISMATCH",
            quality=quality,
            liveness_info=_liveness_info(live_result),
            started=started,
            request_id=request_id,
            extra={"match_score": round(score, 4)},
        )

    # 1:N collision sweep. Runs on rotated search vectors, so nothing is
    # decrypted here - see security/rotation.py.
    rot = database.get_rotation()
    collisions = await matcher.sweep_collisions(
        db,
        rot,
        probe,
        threshold=settings.face_collision_threshold,
        exclude_peserta_id=session["peserta_id"],
    )
    if collisions:
        log.warning(
            "FACE_COLLISION: session %s matches %d other peserta (top %.4f)",
            session["_id"],
            len(collisions),
            collisions[0]["score"],
        )

    latency_ms = int((time.perf_counter() - started) * 1000)
    step_data = {
        "match_score": round(score, 4),
        "threshold": settings.face_match_accept,
        "review_threshold": settings.face_match_review,
        "liveness_score": live_result.score if live_result else None,
        "liveness_method": live_result.method if live_result else None,
        "template_id": template["_id"],
        "latency_ms": latency_ms,
        "quality": quality.model_dump(),
        "collisions": [
            {"peserta_id": str(c["peserta_id"]), "score": c["score"]} for c in collisions
        ],
        "front_camera": meta_obj.get("front_camera"),
    }
    await session_service.advance(db, session, "face", step_data)

    # Mint a FRESH nonce for the fingerprint step rather than reusing the one
    # issued at session start. That one has a 120s TTL and the face step can
    # easily outlive it (retries, a slow upload), which would strand the user at
    # step 2 with NONCE_EXPIRED through no fault of their own.
    fp_nonce = session_service.new_nonce()
    nonce_expires = datetime.now(UTC) + timedelta(seconds=settings.nonce_ttl_seconds)
    await nonce_service.issue(
        db,
        fp_nonce,
        session_id=session["_id"],
        purpose="fingerprint",
        ttl_seconds=settings.nonce_ttl_seconds,
    )
    await db.verification_sessions.update_one(
        {"_id": session["_id"]},
        {"$set": {"nonce": fp_nonce, "nonce_expires_at": nonce_expires}},
    )

    await audit.log_event(
        db,
        session_id=session["_id"],
        step="face",
        outcome="passed",
        peserta_id=session["peserta_id"],
        method=f"{settings.face_rec_model.stem} + {live_result.method if live_result else 'none'}",
        scores={
            "match": round(score, 4),
            "liveness": live_result.score if live_result else None,
            "det": quality.det_score,
        },
        device_uid=session["context"].get("device_uid"),
        faskes_id=session["context"].get("faskes_id"),
        geo=session["context"].get("location", {}).get("geo"),
        latency_ms=latency_ms,
        request_id=request_id,
    )

    return FaceStepResponse(
        result="passed",
        match_score=round(score, 4),
        threshold=settings.face_match_accept,
        liveness=_liveness_info(live_result),
        quality=quality,
        latency_ms=latency_ms,
        next_step="fingerprint",
        nonce=fp_nonce,
        message="Verifikasi wajah berhasil."
        + (" Skor mendekati ambang, akan ditinjau." if verdict == "review" else ""),
    )


# --------------------------------------------------------------------------- #
def _analyse(engine, payloads, challenge, liveness_threshold):
    """Detect on every frame, embed only the best one.

    Embedding is by far the most expensive stage (~90 ms vs ~20 ms for
    detection), so running it once instead of three times is the single biggest
    latency win in the whole request.
    """
    analyses: list[FrameAnalysis] = []
    usable_frames, usable_faces = [], []

    for idx, raw in enumerate(payloads):
        try:
            img = images.decode(raw)
        except ValueError as exc:
            analyses.append(FrameAnalysis(idx, False, str(exc)))
            continue

        code, blur, bright = images.quality_gate(img)
        if code:
            analyses.append(
                FrameAnalysis(idx, False, code, blur_var=blur, brightness=bright, shape=img.shape[:2])
            )
            continue

        faces = engine.detect(img)
        if not faces:
            analyses.append(FrameAnalysis(idx, False, "NO_FACE_DETECTED", blur_var=blur, brightness=bright))
            continue
        if len(faces) > 1:
            analyses.append(FrameAnalysis(idx, False, "MULTIPLE_FACES", blur_var=blur, brightness=bright))
            continue

        face = faces[0]
        if face.short_side < 112:
            analyses.append(
                FrameAnalysis(idx, False, "FACE_TOO_SMALL", face=face, blur_var=blur, brightness=bright)
            )
            continue

        face.sharpness = images.region_sharpness(img, face.bbox)
        analyses.append(FrameAnalysis(idx, True, None, face=face, blur_var=blur, brightness=bright))
        usable_frames.append(img)
        usable_faces.append(face)

    if not usable_faces:
        return analyses, None, None

    live_result = liveness.get_backend().evaluate(
        usable_frames, usable_faces, challenge, liveness_threshold
    )

    best = max(
        range(len(usable_faces)),
        key=lambda i: usable_faces[i].det_score * (usable_faces[i].sharpness or 1.0),
    )
    probe = engine.embed(usable_frames[best], usable_faces[best].kps)
    return analyses, probe, live_result


def _first_failure(analyses: list[FrameAnalysis]) -> str | None:
    """If no frame was usable, report the most common reason - that is the one
    the user can actually act on."""
    if any(a.ok for a in analyses):
        return None
    codes = [a.error_code for a in analyses if a.error_code]
    if not codes:
        return "NO_FACE_DETECTED"
    return max(set(codes), key=codes.count)


def _quality_of(analyses: list[FrameAnalysis]) -> FaceQuality:
    usable = [a for a in analyses if a.ok and a.face is not None]
    if not usable:
        first = analyses[0] if analyses else None
        return FaceQuality(
            blur_var=round(first.blur_var, 1) if first else 0.0,
            brightness=round(first.brightness, 1) if first else 0.0,
        )
    best = max(usable, key=lambda a: a.face.det_score)
    return FaceQuality(
        blur_var=round(best.blur_var, 1),
        brightness=round(best.brightness, 1),
        face_px=int(best.face.short_side),
        det_score=round(best.face.det_score, 4),
    )


def _liveness_info(result) -> LivenessInfo | None:
    if result is None:
        return None
    return LivenessInfo(
        passed=result.passed,
        score=result.score,
        method=result.method,
        signals={k: round(float(v), 4) for k, v in result.signals.items()},
        reason=result.reason,
    )


async def _fail(
    db,
    session,
    settings,
    *,
    code: str,
    quality: FaceQuality,
    liveness_info: LivenessInfo | None,
    started: float,
    request_id: str,
    extra: dict | None = None,
) -> FaceStepResponse:
    """A failed face step is HTTP 200 with result='failed'.

    It is a business outcome the UI must render with a score and a retry count,
    not a protocol error. Returning 4xx here would have Flutter's generic error
    handler swallow it and show "terjadi kesalahan" instead of the real reason.
    """
    latency_ms = int((time.perf_counter() - started) * 1000)
    extra = extra or {}

    updated, attempts, exhausted = await session_service.record_failure(
        db,
        session,
        "face",
        {"error_code": code, "latency_ms": latency_ms, "quality": quality.model_dump(), **extra},
        max_attempts=settings.face_max_attempts,
    )

    await audit.log_event(
        db,
        session_id=session["_id"],
        step="face",
        outcome="failed",
        peserta_id=session["peserta_id"],
        method=settings.face_rec_model.stem,
        scores={
            "match": extra.get("match_score"),
            "liveness": liveness_info.score if liveness_info else None,
            "det": quality.det_score,
        },
        error_code=code,
        device_uid=session["context"].get("device_uid"),
        faskes_id=session["context"].get("faskes_id"),
        geo=session["context"].get("location", {}).get("geo"),
        latency_ms=latency_ms,
        request_id=request_id,
    )

    attempts_left = max(0, settings.face_max_attempts - attempts)
    message = message_for(code)
    if exhausted:
        message = f"{message} Batas percobaan tercapai, sesi ditolak."
    elif attempts_left:
        message = f"{message} Sisa percobaan: {attempts_left}."

    return FaceStepResponse(
        result="failed",
        error_code=code if not exhausted else "MAX_ATTEMPTS",
        message=message,
        match_score=extra.get("match_score"),
        threshold=settings.face_match_accept,
        liveness=liveness_info,
        quality=quality,
        latency_ms=latency_ms,
        attempts_used=attempts,
        attempts_left=attempts_left,
        next_step=None if exhausted else "face",
    )
