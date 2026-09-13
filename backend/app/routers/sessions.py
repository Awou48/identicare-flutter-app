from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter

from app import db as database
from app.deps import CurrentUserDep, DbDep, FacilityDep, RequestIdDep, SessionTokenDep, SettingsDep
from app.schemas.common import OkResponse
from app.schemas.peserta import PesertaFull, PesertaPreview
from app.schemas.session import (
    BiometrikSummary,
    CommitRequest,
    CommitResponse,
    ReviewClaim,
    ReviewConfirm,
    ReviewData,
    SessionCreate,
    SessionCreated,
    SessionState,
)
from app.security import crypto
from app.services import audit, fraud_rules, matcher, session_service
from app.utils.errors import ApiError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/verification", tags=["verification"])


@router.post("/sessions", response_model=SessionCreated, status_code=201)
async def start_session(
    payload: SessionCreate,
    db: DbDep,
    settings: SettingsDep,
    user: CurrentUserDep,
    _faskes_key: FacilityDep,
    request_id: RequestIdDep,
) -> SessionCreated:
    peserta = await db.peserta.find_one({"no_bpjs": payload.no_bpjs})
    if not peserta:
        raise ApiError("PESERTA_NOT_FOUND", 404)

    if peserta.get("status_kepesertaan") == "NONAKTIF":
        raise ApiError("PESERTA_NONAKTIF", 403, details={"status": peserta["status_kepesertaan"]})

    if await matcher.get_active_template(db, peserta["_id"]) is None:
        raise ApiError("BIOMETRIC_NOT_ENROLLED", 409)

    faskes = await db.facilities.find_one({"kode_faskes": payload.kode_faskes})
    if not faskes:
        raise ApiError("FASKES_NOT_FOUND", 404)

    device = await db.devices.find_one({"device_uid": payload.device.device_uid})
    if device and device.get("blocked"):
        raise ApiError("DEVICE_BLOCKED", 423)

    since = datetime.now(UTC) - timedelta(hours=1)
    recent = await db.verification_sessions.count_documents(
        {"peserta_id": peserta["_id"], "created_at": {"$gte": since}}
    )
    if recent >= settings.sessions_per_hour:
        raise ApiError("TOO_MANY_SESSIONS", 429, details={"sessions_last_hour": recent})

    session = await session_service.create(
        db,
        peserta=peserta,
        faskes=faskes,
        claim=payload.claim.model_dump(),
        context={
            "channel": "mobile_app",
            "device_id": device["_id"] if device else None,
            "device_uid": payload.device.device_uid,
            "firebase_uid": user.uid,
            "app_version": payload.device.app_version,
            "platform": payload.device.platform,
        },
        ttl_seconds=settings.session_ttl_seconds,
        nonce_ttl_seconds=settings.nonce_ttl_seconds,
    )

    if device:
        await db.devices.update_one(
            {"_id": device["_id"]},
            {
                "$addToSet": {"peserta_ids": peserta["_id"]},
                "$set": {"last_seen": datetime.now(UTC)},
            },
        )

    await audit.log_event(
        db,
        session_id=session["_id"],
        step="session",
        outcome="started",
        peserta_id=peserta["_id"],
        device_uid=payload.device.device_uid,
        faskes_id=faskes["_id"],
        geo=faskes.get("geo"),
        request_id=request_id,
    )

    return SessionCreated(
        session_id=str(session["_id"]),
        session_token=session["session_token"],
        expires_at=session["expires_at"],
        required_steps=session["required_steps"],
        current_step="face",
        nonce=session["nonce"],
        nonce_expires_at=session["nonce_expires_at"],
        peserta_preview=PesertaPreview(
            nama_masked=crypto.mask_name(peserta["nama_lengkap"]),
            no_bpjs_masked=crypto.mask_bpjs(peserta["no_bpjs"]),
            biometric_enrolled=bool(peserta.get("biometric_enrolled")),
        ),
    )


@router.get("/sessions/{session_id}", response_model=SessionState)
async def get_session(
    session_id: str, db: DbDep, token: SessionTokenDep, _user: CurrentUserDep
) -> SessionState:
    """Resume. The client can be killed at any step and pick up exactly here."""
    session = await session_service.load(db, session_id, token)
    return SessionState(**session_service.public_view(session))


@router.post("/sessions/{session_id}/cancel", response_model=OkResponse)
async def cancel_session(
    session_id: str,
    db: DbDep,
    token: SessionTokenDep,
    _user: CurrentUserDep,
    request_id: RequestIdDep,
) -> OkResponse:
    session = await session_service.load(db, session_id, token)
    await session_service.cancel(db, session)
    await audit.log_event(
        db,
        session_id=session["_id"],
        step="session",
        outcome="cancelled",
        peserta_id=session["peserta_id"],
        request_id=request_id,
    )
    return OkResponse()


@router.get("/sessions/{session_id}/review", response_model=ReviewData)
async def get_review(session_id: str, db: DbDep, token: SessionTokenDep, _user: CurrentUserDep) -> ReviewData:
    session = await session_service.load(db, session_id, token)
    await session_service.assert_live(db, session)
    session_service.require_state(session, "review")

    peserta = await db.peserta.find_one({"_id": session["peserta_id"]})
    if not peserta:
        raise ApiError("PESERTA_NOT_FOUND", 404)

    faskes = await db.facilities.find_one({"_id": session["context"]["faskes_id"]})

    nik_masked = "****"
    if peserta.get("nik_enc"):
        kek = database.get_kek()
        aad = crypto.build_aad(peserta["_id"], "nik", 1)
        try:
            nik = crypto.decrypt_blob(kek, peserta["nik_enc"], aad).decode()
            nik_masked = crypto.mask_nik(nik)
            del nik
        except Exception:
            log.exception("NIK decrypt failed for peserta %s", peserta["_id"])
        await audit.record(
            db,
            who=session["context"].get("firebase_uid", "unknown"),
            what="decrypt_nik",
            peserta_id=peserta["_id"],
            session_id=session["_id"],
            purpose="tampilkan_review",
        )
    elif peserta.get("nik_last4"):
        nik_masked = f"************{peserta['nik_last4']}"

    steps = session.get("steps", {})
    claim = session.get("claim", {})

    return ReviewData(
        peserta=PesertaFull(
            nama_lengkap=peserta["nama_lengkap"],
            no_bpjs=peserta["no_bpjs"],
            nik_masked=nik_masked,
            tanggal_lahir=peserta.get("tanggal_lahir"),
            jenis_kelamin=peserta.get("jenis_kelamin"),
            kelas_rawat=peserta.get("kelas_rawat"),
            jenis_peserta=peserta.get("jenis_peserta"),
            status_kepesertaan=peserta["status_kepesertaan"],
            tunggakan_bulan=peserta.get("tunggakan_bulan", 0),
            faskes_tingkat1=(peserta.get("faskes_tingkat1") or {}).get("nama"),
        ),
        claim=ReviewClaim(
            claim_ref=claim.get("claim_ref"),
            jenis_layanan=claim.get("jenis_layanan", "RAWAT_JALAN"),
            poli=claim.get("poli", ""),
            estimasi_biaya=claim.get("estimasi_biaya", 0),
            faskes=faskes["nama"] if faskes else "",
        ),
        biometrik=BiometrikSummary(
            wajah={
                "passed": steps.get("face", {}).get("status") == "passed",
                "score": steps.get("face", {}).get("match_score"),
                "liveness": steps.get("face", {}).get("liveness_score"),
            },
            sidik_jari={
                "passed": steps.get("fingerprint", {}).get("status") == "passed",
                "security_level": steps.get("fingerprint", {}).get("security_level"),
                "method": steps.get("fingerprint", {}).get("method"),
            },
        ),
        risk=session.get("risk", {}),
    )


@router.post("/sessions/{session_id}/review")
async def confirm_review(
    session_id: str,
    payload: ReviewConfirm,
    db: DbDep,
    token: SessionTokenDep,
    _user: CurrentUserDep,
    request_id: RequestIdDep,
) -> dict:
    session = await session_service.load(db, session_id, token)
    await session_service.assert_live(db, session)
    session_service.require_state(session, "review")

    if not payload.confirmed:
        raise ApiError("REVIEW_NOT_CONFIRMED", 400)

    await session_service.advance(
        db,
        session,
        "review",
        {
            "fields_shown": ["nama", "no_bpjs", "nik_masked", "kelas", "faskes"],
            "confirmed_by": "peserta",
            "corrections": payload.corrections,
        },
    )
    await audit.log_event(
        db,
        session_id=session["_id"],
        step="review",
        outcome="passed",
        peserta_id=session["peserta_id"],
        request_id=request_id,
    )
    return {"status": "ok", "step": "review", "result": "passed", "next_step": "commit"}


@router.post("/sessions/{session_id}/commit", response_model=CommitResponse)
async def commit(
    session_id: str,
    payload: CommitRequest,
    db: DbDep,
    token: SessionTokenDep,
    _user: CurrentUserDep,
    request_id: RequestIdDep,
) -> CommitResponse:
    """Final decision."""
    session = await session_service.load(db, session_id, token)

    if session["status"] == "committed":
        result = session.get("result") or {}
        if session.get("idempotency_key") == payload.idempotency_key:
            return _commit_response(session, result)
        raise ApiError("SESSION_CLOSED", 409, details={"status": "committed"})

    await session_service.assert_live(db, session)
    session_service.require_state(session, "commit")

    steps = session.get("steps", {})
    incomplete = [
        name
        for name in session.get("required_steps", session_service.REQUIRED_STEPS)
        if steps.get(name, {}).get("status") != "passed"
    ]
    if incomplete:
        raise ApiError("STEPS_INCOMPLETE", 409, details={"incomplete": incomplete})

    peserta = await db.peserta.find_one({"_id": session["peserta_id"]})
    if not peserta:
        raise ApiError("PESERTA_NOT_FOUND", 404)

    collisions = steps.get("face", {}).get("collisions") or []
    score, band, decision, signals = await fraud_rules.evaluate(
        db, session, peserta=peserta, face_collisions=collisions
    )
    await fraud_rules.persist(db, signals, peserta_id=peserta["_id"], session_id=session["_id"])

    now = datetime.now(UTC)
    receipt = None
    if decision != "REJECTED":
        receipt = session_service.receipt_number(await session_service.next_receipt_seq(db), now)

    result = {
        "decision": decision,
        "reason_code": signals[0].rule_id if (decision == "REJECTED" and signals) else None,
        "reason_id": None,
        "receipt_no": receipt,
        "decided_at": now,
    }
    risk = {
        "score": score,
        "band": band,
        "signals": [s.to_dict() for s in signals],
        "evaluated_at": now,
    }

    updated = await db.verification_sessions.find_one_and_update(
        {"_id": session["_id"], "status": "reviewed"},
        {
            "$set": {
                "status": "committed" if decision != "REJECTED" else "rejected",
                "steps.commit.status": "passed",
                "steps.commit.at": now,
                "steps.commit.decision": decision,
                "result": result,
                "risk": risk,
                "idempotency_key": payload.idempotency_key,
                "updated_at": now,
            }
        },
        return_document=True,
    )
    if updated is None:
        raise ApiError("STEP_OUT_OF_ORDER", 409, details={"reason": "sesi berubah bersamaan"})

    await audit.log_event(
        db,
        session_id=session["_id"],
        step="commit",
        outcome="passed" if decision != "REJECTED" else "failed",
        peserta_id=peserta["_id"],
        method="fraud_rules_v1",
        scores={"risk": score},
        error_code=result["reason_code"],
        device_uid=session["context"].get("device_uid"),
        faskes_id=session["context"].get("faskes_id"),
        geo=session["context"].get("location", {}).get("geo"),
        request_id=request_id,
    )

    return _commit_response(updated, result)


def _commit_response(session: dict, result: dict) -> CommitResponse:
    steps = session.get("steps", {})
    risk = session.get("risk", {})
    location = session.get("context", {}).get("location", {})
    decided = result.get("decided_at") or datetime.now(UTC)
    if decided.tzinfo is None:
        decided = decided.replace(tzinfo=UTC)
    wib = decided + timedelta(hours=7)

    return CommitResponse(
        decision=result.get("decision", "REVIEW"),
        receipt_no=result.get("receipt_no"),
        decided_at=decided,
        risk={
            "score": risk.get("score", 0),
            "band": risk.get("band", "LOW"),
            "signals": risk.get("signals", []),
        },
        summary={
            "wajah": steps.get("face", {}).get("match_score"),
            "sidik_jari": steps.get("fingerprint", {}).get("security_level"),
            "faskes": location.get("label"),
            "waktu": f"{wib:%d %b %Y, %H:%M} WIB",
        },
    )
