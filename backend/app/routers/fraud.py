"""Fraud signals. Operator-facing - these feed the hospital/BPJS dashboard,
which is a second client outside the scope of the Flutter app.
"""

from __future__ import annotations

from datetime import UTC, datetime

from bson import ObjectId
from fastapi import APIRouter, Query

from app.deps import DbDep, OperatorDep
from app.services import fraud_rules
from app.utils.errors import ApiError

router = APIRouter(prefix="/fraud", tags=["fraud"])


@router.post("/check")
async def check(payload: dict, db: DbDep, _: OperatorDep) -> dict:
    """Ad-hoc evaluation against a session, without committing it."""
    session_id = payload.get("session_id")
    if not session_id:
        raise ApiError("VALIDATION_ERROR", 422, details={"field": "session_id"})
    try:
        oid = ObjectId(session_id)
    except Exception as exc:
        raise ApiError("SESSION_NOT_FOUND", 404) from exc

    session = await db.verification_sessions.find_one({"_id": oid})
    if not session:
        raise ApiError("SESSION_NOT_FOUND", 404)

    peserta = await db.peserta.find_one({"_id": session["peserta_id"]})
    if not peserta:
        raise ApiError("PESERTA_NOT_FOUND", 404)

    collisions = session.get("steps", {}).get("face", {}).get("collisions") or []
    score, band, decision, signals = await fraud_rules.evaluate(
        db, session, peserta=peserta, face_collisions=collisions
    )
    return {
        "status": "ok",
        "score": score,
        "band": band,
        "recommendation": decision,
        "signals": [s.to_dict() for s in signals],
    }


@router.get("/signals")
async def list_signals(
    db: DbDep,
    _: OperatorDep,
    status_filter: str | None = Query(default="open", alias="status"),
    severity: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    query: dict = {}
    if status_filter:
        query["status"] = status_filter
    if severity:
        query["severity"] = severity

    docs = (
        await db.fraud_signals.find(query)
        .sort([("detected_at", -1)])
        .limit(limit)
        .to_list(limit)
    )
    peserta_ids = list({d["peserta_id"] for d in docs})
    names = {
        p["_id"]: p["nama_lengkap"]
        async for p in db.peserta.find({"_id": {"$in": peserta_ids}}, {"nama_lengkap": 1})
    }

    return {
        "status": "ok",
        "items": [
            {
                "signal_id": str(d["_id"]),
                "peserta_id": str(d["peserta_id"]),
                "peserta_nama": names.get(d["peserta_id"]),
                "session_id": str(d["session_id"]) if d.get("session_id") else None,
                "rule_id": d["rule_id"],
                "severity": d["severity"],
                "weight": d["weight"],
                "title": d["title"],
                "detail": d.get("detail", {}),
                "status": d["status"],
                "detected_at": d["detected_at"],
            }
            for d in docs
        ],
        "count": len(docs),
    }


@router.post("/signals/{signal_id}/resolve")
async def resolve_signal(signal_id: str, payload: dict, db: DbDep, _: OperatorDep) -> dict:
    new_status = payload.get("status", "dismissed")
    if new_status not in {"reviewing", "confirmed", "dismissed"}:
        raise ApiError("VALIDATION_ERROR", 422, details={"status": new_status})
    try:
        oid = ObjectId(signal_id)
    except Exception as exc:
        raise ApiError("VALIDATION_ERROR", 422, details={"field": "signal_id"}) from exc

    result = await db.fraud_signals.update_one(
        {"_id": oid},
        {
            "$set": {
                "status": new_status,
                "resolved_at": datetime.now(UTC),
                "resolved_by": payload.get("resolved_by", "operator"),
            }
        },
    )
    if result.matched_count == 0:
        raise ApiError("VALIDATION_ERROR", 404, details={"signal_id": signal_id})
    return {"status": "ok", "signal_id": signal_id, "new_status": new_status}


@router.get("/rules")
async def list_rules(_: OperatorDep) -> dict:
    """Document the rule set so the dashboard does not hardcode it."""
    return {
        "status": "ok",
        "bands": {"LOW": "0-39 -> APPROVED", "MEDIUM": "40-69 -> REVIEW", "HIGH": ">=70 -> REJECTED"},
        "note": "Sinyal dengan severity 'critical' langsung menghasilkan REJECTED.",
        "rules": [
            {"rule_id": "SIMULTANEOUS_CLAIM", "weight": 40, "severity": "critical",
             "window_hours": fraud_rules.SIMULTANEOUS_WINDOW_HOURS},
            {"rule_id": "FACE_COLLISION", "weight": 35, "severity": "critical"},
            {"rule_id": "IMPOSSIBLE_TRAVEL", "weight": 30, "severity": "high",
             "max_kmh": fraud_rules.IMPOSSIBLE_TRAVEL_KMH},
            {"rule_id": "HIGH_FREQUENCY_CLAIM", "weight": 25, "severity": "high",
             "limit": fraud_rules.HIGH_FREQUENCY_LIMIT, "days": fraud_rules.HIGH_FREQUENCY_DAYS},
            {"rule_id": "SHARED_DEVICE", "weight": 20, "severity": "medium",
             "limit": fraud_rules.SHARED_DEVICE_LIMIT, "days": fraud_rules.SHARED_DEVICE_DAYS},
            {"rule_id": "PESERTA_MENUNGGAK", "weight": 15, "severity": "medium"},
            {"rule_id": "REPEATED_FAILED_ATTEMPTS", "weight": 15, "severity": "medium",
             "limit": fraud_rules.FAILED_ATTEMPT_LIMIT, "hours": fraud_rules.FAILED_ATTEMPT_HOURS},
            {"rule_id": "LOW_MATCH_MARGIN", "weight": 10, "severity": "low"},
            {"rule_id": "SOFTWARE_KEY_ONLY", "weight": 10, "severity": "low"},
            {"rule_id": "OFF_HOURS", "weight": 5, "severity": "info"},
        ],
    }
