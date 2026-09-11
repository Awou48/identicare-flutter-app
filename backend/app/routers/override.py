"""Break-glass: staff override when biometrics legitimately cannot pass.

WHY THIS EXISTS. Before it, three failed face attempts rejected the session and
that was the end. The proposal itself names faces unscannable because of bruising
or swelling, and fingers unreadable after burns. So the system as built denied
care to exactly the vulnerable groups it claims to serve. That is not an edge
case - in a trauma ward it is Tuesday.

DESIGN PRINCIPLE: the override must be MORE expensive and MORE visible than the
happy path. Otherwise it stops being a safety valve and becomes the fraud
mechanism - the easiest route for an insider is always the one with the fewest
checks. Hence:

  * two distinct staff members, the approver holding `supervisor`,
  * a reason code from a fixed enum (free text alone is unanalysable),
  * photographs of the physical BPJS card and KTP, encrypted at rest,
  * the failed attempts already in verification_events stand as evidence,
  * the decision is APPROVED_WITH_OVERRIDE, never plain APPROVED,
  * two fraud signals fire, one of them critical above a per-staff frequency.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from bson import ObjectId
from fastapi import APIRouter, File, Form, UploadFile

from app import db as database
from app.db_schema import OVERRIDE_REASONS
from app.deps import DbDep, RequestIdDep, SessionTokenDep, SettingsDep, StaffDep, SupervisorDep
from app.security import crypto
from app.services import audit, fraud_rules, session_service
from app.utils.errors import ApiError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/verification/sessions", tags=["override"])

# A nurse has to physically find a supervisor. The normal 10-minute session TTL
# is far too short for that, so requesting an override extends the window -
# otherwise the feature would be unusable in the exact situation it exists for.
APPROVAL_WINDOW = timedelta(minutes=30)

MAX_EVIDENCE_BYTES = 5 * 1024 * 1024


@router.post("/{session_id}/override/request")
async def request_override(
    session_id: str,
    db: DbDep,
    settings: SettingsDep,
    token: SessionTokenDep,
    staff: StaffDep,
    request_id: RequestIdDep,
    reason_code: str = Form(...),
    reason_note: str = Form(""),
    evidence_bpjs: UploadFile | None = File(None),
    evidence_ktp: UploadFile | None = File(None),
) -> dict:
    """Petugas escalates a rejected session for supervisor approval."""
    session = await session_service.load(db, session_id, token)

    if session["status"] not in session_service.OVERRIDE_ELIGIBLE:
        raise ApiError(
            "OVERRIDE_NOT_ELIGIBLE",
            409,
            message="Override hanya dapat diajukan setelah verifikasi biometrik gagal.",
            details={
                "status": session["status"],
                "eligible_from": sorted(session_service.OVERRIDE_ELIGIBLE),
            },
        )

    if reason_code not in OVERRIDE_REASONS:
        raise ApiError(
            "VALIDATION_ERROR",
            422,
            details={"reason_code": reason_code, "allowed": OVERRIDE_REASONS},
        )
    if reason_code == "LAINNYA" and len(reason_note.strip()) < 10:
        raise ApiError(
            "OVERRIDE_REASON_REQUIRED",
            422,
            message="Alasan 'LAINNYA' wajib dijelaskan minimal 10 karakter.",
        )

    # Evidence is how a reviewer later reconstructs whether the override was
    # justified. Without it the audit trail records only that someone asserted
    # a reason.
    kek = database.get_kek()
    evidence: dict[str, object] = {}
    for label, upload in (("bpjs_card", evidence_bpjs), ("ktp", evidence_ktp)):
        if upload is None:
            continue
        blob = await upload.read()
        if len(blob) > MAX_EVIDENCE_BYTES:
            raise ApiError("IMAGE_TOO_LARGE", 413, details={"field": label})
        aad = crypto.build_aad(session["_id"], f"override_{label}", 1)
        evidence[label] = crypto.encrypt_blob(kek, blob, aad)

    now = datetime.now(UTC)
    face = session.get("steps", {}).get("face", {})
    fingerprint = session.get("steps", {}).get("fingerprint", {})

    updated = await db.verification_sessions.find_one_and_update(
        {"_id": session["_id"], "status": "rejected"},
        {
            "$set": {
                "status": session_service.OVERRIDE_PENDING,
                "override": {
                    "status": "pending",
                    "reason_code": reason_code,
                    "reason_note": reason_note.strip() or None,
                    "requested_by": ObjectId(staff.staff_id),
                    "requested_by_nama": staff.nama,
                    "requested_at": now,
                    "approved_by": None,
                    "evidence": evidence,
                    # Snapshot of WHY biometrics failed, so a reviewer does not
                    # have to reconstruct it from the event log.
                    "failed_evidence": {
                        "face_attempts": face.get("attempts"),
                        "face_error": face.get("error_code"),
                        "face_score": face.get("match_score"),
                        "fingerprint_attempts": fingerprint.get("attempts"),
                        "fingerprint_error": fingerprint.get("error_code"),
                    },
                },
                # Extend the clock: the approver has to walk over here.
                "expires_at": now + APPROVAL_WINDOW,
                "updated_at": now,
            }
        },
        return_document=True,
    )
    if updated is None:
        raise ApiError("OVERRIDE_NOT_ELIGIBLE", 409, details={"reason": "sesi berubah bersamaan"})

    await audit.log_event(
        db,
        session_id=session["_id"],
        step="session",
        outcome="started",
        peserta_id=session["peserta_id"],
        method=f"override_request:{reason_code}",
        device_uid=session["context"].get("device_uid"),
        faskes_id=session["context"].get("faskes_id"),
        request_id=request_id,
    )
    log.warning(
        "override requested for session %s by staff %s reason=%s",
        session_id,
        staff.staff_id,
        reason_code,
    )

    return {
        "status": "ok",
        "session_id": session_id,
        "override_status": "pending",
        "reason_code": reason_code,
        "evidence_attached": sorted(evidence),
        "expires_at": updated["expires_at"],
        "message": "Menunggu persetujuan supervisor.",
    }


@router.post("/{session_id}/override/approve")
async def approve_override(
    session_id: str,
    payload: dict,
    db: DbDep,
    settings: SettingsDep,
    token: SessionTokenDep,
    supervisor: SupervisorDep,
    request_id: RequestIdDep,
) -> dict:
    """Supervisor approves. Commits the claim as APPROVED_WITH_OVERRIDE."""
    session = await session_service.load(db, session_id, token)
    await session_service.assert_live(db, session)

    if session["status"] != session_service.OVERRIDE_PENDING:
        raise ApiError(
            "OVERRIDE_NOT_PENDING",
            409,
            details={"status": session["status"], "expected": session_service.OVERRIDE_PENDING},
        )

    override = session.get("override") or {}
    requested_by = override.get("requested_by")

    # FOUR EYES. Checked against what is stored, never against anything the
    # client claims. A single compromised account must not be able to both
    # request and approve.
    if requested_by is not None and str(requested_by) == supervisor.staff_id:
        raise ApiError(
            "FOUR_EYES_REQUIRED",
            403,
            message="Override harus disetujui oleh petugas yang berbeda dari pengaju.",
            details={"requested_by": str(requested_by)},
        )

    peserta = await db.peserta.find_one({"_id": session["peserta_id"]})
    if not peserta:
        raise ApiError("PESERTA_NOT_FOUND", 404)

    now = datetime.now(UTC)

    # Write the approval BEFORE evaluating, because the fraud rules read
    # `override.approved_by` to compute MANUAL_OVERRIDE and the per-staff
    # frequency. Evaluating first would always score the override as absent.
    session["override"] = {
        **override,
        "status": "approved",
        "approved_by": ObjectId(supervisor.staff_id),
        "approved_by_nama": supervisor.nama,
        "approved_at": now,
        "supervisor_note": (payload.get("note") or "").strip() or None,
    }
    await db.verification_sessions.update_one(
        {"_id": session["_id"]}, {"$set": {"override": session["override"]}}
    )

    score, band, decision, signals = await fraud_rules.evaluate(
        db, session, peserta=peserta, face_collisions=[]
    )

    # An override never yields a clean APPROVED. If the rules would have said
    # APPROVED, it becomes APPROVED_WITH_OVERRIDE; a REJECTED verdict still
    # stands, because an override is for failed biometrics, not for overruling
    # duplicate-claim or face-collision findings.
    final_decision = "APPROVED_WITH_OVERRIDE" if decision != "REJECTED" else "REJECTED"

    await fraud_rules.persist(db, signals, peserta_id=peserta["_id"], session_id=session["_id"])

    receipt = None
    if final_decision != "REJECTED":
        receipt = session_service.receipt_number(await session_service.next_receipt_seq(db), now)

    result = {
        "decision": final_decision,
        "reason_code": override.get("reason_code"),
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
        {"_id": session["_id"], "status": session_service.OVERRIDE_PENDING},
        {
            "$set": {
                "status": "committed" if final_decision != "REJECTED" else "rejected",
                "steps.commit.status": "passed",
                "steps.commit.at": now,
                "steps.commit.decision": final_decision,
                "result": result,
                "risk": risk,
                "updated_at": now,
            }
        },
        return_document=True,
    )
    if updated is None:
        raise ApiError("OVERRIDE_NOT_PENDING", 409, details={"reason": "sesi berubah bersamaan"})

    await audit.log_event(
        db,
        session_id=session["_id"],
        step="commit",
        outcome="passed" if final_decision != "REJECTED" else "failed",
        peserta_id=peserta["_id"],
        method=f"override_approved_by:{supervisor.staff_id}",
        scores={"risk": score},
        device_uid=session["context"].get("device_uid"),
        faskes_id=session["context"].get("faskes_id"),
        geo=session["context"].get("location", {}).get("geo"),
        request_id=request_id,
    )
    await audit.record(
        db,
        who=f"staff:{supervisor.staff_id}",
        what="approve_override",
        peserta_id=peserta["_id"],
        session_id=session["_id"],
        purpose=f"override:{override.get('reason_code')}",
    )
    log.warning(
        "OVERRIDE APPROVED session=%s supervisor=%s decision=%s risk=%d",
        session_id,
        supervisor.staff_id,
        final_decision,
        score,
    )

    return {
        "status": "ok",
        "decision": final_decision,
        "receipt_no": receipt,
        "decided_at": now,
        "risk": {"score": score, "band": band, "signals": risk["signals"]},
        "override": {
            "reason_code": override.get("reason_code"),
            "requested_by": str(requested_by) if requested_by else None,
            "approved_by": supervisor.staff_id,
        },
    }


@router.post("/{session_id}/override/reject")
async def reject_override(
    session_id: str,
    payload: dict,
    db: DbDep,
    token: SessionTokenDep,
    supervisor: SupervisorDep,
    request_id: RequestIdDep,
) -> dict:
    session = await session_service.load(db, session_id, token)

    if session["status"] != session_service.OVERRIDE_PENDING:
        raise ApiError("OVERRIDE_NOT_PENDING", 409, details={"status": session["status"]})

    now = datetime.now(UTC)
    note = (payload.get("note") or "").strip()
    await db.verification_sessions.update_one(
        {"_id": session["_id"], "status": session_service.OVERRIDE_PENDING},
        {
            "$set": {
                "status": "override_rejected",
                "override.status": "rejected",
                "override.approved_by": ObjectId(supervisor.staff_id),
                "override.approved_at": now,
                "override.supervisor_note": note or None,
                "result": {
                    "decision": "REJECTED",
                    "reason_code": "OVERRIDE_REJECTED",
                    "reason_id": None,
                    "receipt_no": None,
                    "decided_at": now,
                },
                "updated_at": now,
            }
        },
    )
    await audit.log_event(
        db,
        session_id=session["_id"],
        step="commit",
        outcome="failed",
        peserta_id=session["peserta_id"],
        method=f"override_rejected_by:{supervisor.staff_id}",
        error_code="OVERRIDE_REJECTED",
        request_id=request_id,
    )
    return {"status": "ok", "session_id": session_id, "override_status": "rejected"}


@router.get("/{session_id}/override")
async def get_override(session_id: str, db: DbDep, token: SessionTokenDep) -> dict:
    """Read the override record. Evidence blobs are never returned - they are
    operator-only and read through the auditor console with an audit entry."""
    session = await session_service.load(db, session_id, token)
    override = session.get("override") or {}
    if not override:
        raise ApiError("OVERRIDE_NOT_FOUND", 404)
    return {
        "status": "ok",
        "session_status": session["status"],
        "override": {
            "status": override.get("status"),
            "reason_code": override.get("reason_code"),
            "reason_note": override.get("reason_note"),
            "requested_by_nama": override.get("requested_by_nama"),
            "requested_at": override.get("requested_at"),
            "approved_by_nama": override.get("approved_by_nama"),
            "approved_at": override.get("approved_at"),
            "evidence_attached": sorted(override.get("evidence") or {}),
            "failed_evidence": override.get("failed_evidence", {}),
        },
    }
