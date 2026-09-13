from __future__ import annotations

import base64
import binascii
import json
from datetime import UTC, datetime

from bson import ObjectId
from fastapi import APIRouter, Query

from app.deps import CurrentUserDep, DbDep
from app.schemas.session import HistoryItem, HistoryPage
from app.services import session_service
from app.utils.errors import ApiError

router = APIRouter(prefix="/verification", tags=["history"])


def _encode_cursor(created_at: datetime, oid: ObjectId) -> str:
    raw = json.dumps({"t": created_at.isoformat(), "id": str(oid)})
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, ObjectId]:
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(data["t"]), ObjectId(data["id"])
    except (ValueError, KeyError, binascii.Error) as exc:
        raise ApiError("VALIDATION_ERROR", 422, details={"field": "cursor"}) from exc


async def _resolve_peserta(db, firebase_uid: str) -> dict:
    peserta = await db.peserta.find_one({"firebase_uid": firebase_uid})
    if not peserta:
        raise ApiError(
            "PESERTA_NOT_FOUND",
            404,
            message="Akun ini belum tertaut dengan data peserta BPJS.",
        )
    return peserta


@router.get("/history", response_model=HistoryPage)
async def list_history(
    db: DbDep,
    user: CurrentUserDep,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
) -> HistoryPage:
    """A user sees only their own history."""
    peserta = await _resolve_peserta(db, user.uid)

    query: dict = {"peserta_id": peserta["_id"], "result": {"$ne": None}}
    if status_filter:
        query["result.decision"] = status_filter.upper()
    if cursor:
        created_at, oid = _decode_cursor(cursor)
        query["$or"] = [
            {"created_at": {"$lt": created_at}},
            {"created_at": created_at, "_id": {"$lt": oid}},
        ]

    docs = (
        await db.verification_sessions.find(query)
        .sort([("created_at", -1), ("_id", -1)])
        .limit(limit + 1)
        .to_list(limit + 1)
    )

    has_more = len(docs) > limit
    docs = docs[:limit]

    items = [_to_item(d) for d in docs]
    next_cursor = _encode_cursor(docs[-1]["created_at"], docs[-1]["_id"]) if has_more and docs else None
    return HistoryPage(items=items, next_cursor=next_cursor, has_more=has_more)


def _to_item(doc: dict) -> HistoryItem:
    steps = doc.get("steps", {})
    result = doc.get("result") or {}
    location = doc.get("context", {}).get("location", {})

    metode = []
    if steps.get("face", {}).get("status") == "passed":
        metode.append("wajah")
    if steps.get("fingerprint", {}).get("status") == "passed":
        metode.append("sidik_jari")

    decided = result.get("decided_at") or doc["created_at"]
    if decided.tzinfo is None:
        decided = decided.replace(tzinfo=UTC)

    return HistoryItem(
        session_id=str(doc["_id"]),
        receipt_no=result.get("receipt_no"),
        tanggal=decided,
        metode=metode,
        status=result.get("decision", doc.get("status", "")),
        lokasi={
            "faskes": location.get("label"),
            "kode_faskes": doc.get("context", {}).get("kode_faskes"),
            "geo": location.get("geo"),
        },
        skor={
            "wajah": steps.get("face", {}).get("match_score"),
            "liveness": steps.get("face", {}).get("liveness_score"),
        },
        risk_band=doc.get("risk", {}).get("band", "LOW"),
    )


@router.get("/history/{session_id}")
async def history_detail(session_id: str, db: DbDep, user: CurrentUserDep) -> dict:
    """Full audit trail for one session, including every failed attempt."""
    peserta = await _resolve_peserta(db, user.uid)
    try:
        oid = ObjectId(session_id)
    except Exception as exc:
        raise ApiError("SESSION_NOT_FOUND", 404) from exc

    session = await db.verification_sessions.find_one({"_id": oid, "peserta_id": peserta["_id"]})
    if not session:
        raise ApiError("SESSION_NOT_FOUND", 404)

    events = await db.verification_events.find({"session_id": oid}).sort([("seq", 1)]).to_list(200)

    return {
        "status": "ok",
        "session": session_service.public_view(session),
        "lokasi": session.get("context", {}).get("location", {}),
        "claim": session.get("claim", {}),
        "events": [
            {
                "seq": e["seq"],
                "step": e["step"],
                "outcome": e["outcome"],
                "method": e.get("method"),
                "scores": e.get("scores", {}),
                "error_code": e.get("error_code"),
                "latency_ms": e.get("latency_ms"),
                "at": e["at"],
            }
            for e in events
        ],
    }
