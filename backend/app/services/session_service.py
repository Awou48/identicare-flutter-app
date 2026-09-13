from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase

from app.security import crypto
from app.utils.errors import ApiError

NEXT_STEP: dict[str, str | None] = {
    "created": "face",
    "face_passed": "fingerprint",
    "fingerprint_passed": "review",
    "reviewed": "commit",
    "committed": None,
    "rejected": None,
    "expired": None,
    "cancelled": None,
    "override_pending": None,
    "override_rejected": None,
}

STEP_TO_STATE = {
    "face": "face_passed",
    "fingerprint": "fingerprint_passed",
    "review": "reviewed",
    "commit": "committed",
}

TERMINAL = {"committed", "expired", "cancelled", "override_rejected"}

OVERRIDE_ELIGIBLE = {"rejected"}
OVERRIDE_PENDING = "override_pending"

REQUIRED_STEPS = ["face", "fingerprint", "review"]


def new_token() -> str:
    return secrets.token_hex(32)


def new_nonce() -> str:
    return secrets.token_hex(32)


def receipt_number(seq: int, when: datetime | None = None) -> str:
    when = when or datetime.now(UTC)
    return f"VRF-{when:%Y%m%d}-{seq:06d}"


async def create(
    db: AsyncDatabase,
    *,
    peserta: dict,
    faskes: dict,
    claim: dict,
    context: dict,
    ttl_seconds: int,
    nonce_ttl_seconds: int,
) -> dict:
    now = datetime.now(UTC)
    nonce = new_nonce()
    doc = {
        "session_token": new_token(),
        "status": "created",
        "peserta_id": peserta["_id"],
        "no_bpjs": peserta["no_bpjs"],
        "claim": claim,
        "context": {
            **context,
            "faskes_id": faskes["_id"],
            "kode_faskes": faskes["kode_faskes"],
            "location": {
                "source": "faskes",
                "geo": faskes["geo"],
                "accuracy_m": None,
                "label": f"{faskes['nama']}, {faskes.get('kota', '')}".strip(", "),
            },
        },
        "required_steps": list(REQUIRED_STEPS),
        "nonce": nonce,
        "nonce_expires_at": now + timedelta(seconds=nonce_ttl_seconds),
        "steps": {
            "face": {"status": "pending", "attempts": 0},
            "fingerprint": {"status": "pending", "attempts": 0},
            "review": {"status": "pending"},
            "commit": {"status": "pending"},
        },
        "risk": {"score": 0, "band": "LOW", "signals": []},
        "result": None,
        "idempotency_key": None,
        "created_at": now,
        "updated_at": now,
        "expires_at": now + timedelta(seconds=ttl_seconds),
        "schema_version": 1,
    }
    result = await db.verification_sessions.insert_one(doc)
    doc["_id"] = result.inserted_id

    await db.nonces.insert_one(
        {
            "_id": nonce,
            "session_id": doc["_id"],
            "purpose": "fingerprint",
            "used": False,
            "issued_at": now,
            "expires_at": now + timedelta(seconds=nonce_ttl_seconds),
        }
    )
    return doc


async def load(db: AsyncDatabase, session_id: str, token: str) -> dict:
    """Fetch and authorise. Raises ApiError for every failure mode."""
    try:
        oid = ObjectId(session_id)
    except Exception as exc:
        raise ApiError("SESSION_NOT_FOUND", 404) from exc

    session = await db.verification_sessions.find_one({"_id": oid})
    if not session:
        raise ApiError("SESSION_NOT_FOUND", 404)

    if not crypto.constant_time_equals(session["session_token"], token or ""):
        raise ApiError("INVALID_SESSION_TOKEN", 403)

    return session


async def assert_live(db: AsyncDatabase, session: dict) -> dict:
    """Expire the session if its clock ran out. 410 rather than 404: the resource existed, the client just
    took too long, and the UI message differs.
    """
    if session["status"] in TERMINAL:
        if session["status"] == "expired":
            raise ApiError("SESSION_EXPIRED", 410)
        raise ApiError("SESSION_CLOSED", 409, details={"status": session["status"]})

    expires_at = session["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if datetime.now(UTC) >= expires_at:
        await db.verification_sessions.update_one(
            {"_id": session["_id"], "status": {"$nin": list(TERMINAL)}},
            {"$set": {"status": "expired", "updated_at": datetime.now(UTC)}},
        )
        raise ApiError("SESSION_EXPIRED", 410)
    return session


def require_state(session: dict, step: str) -> None:
    """The guard. Posting a step out of order is 409, never a silent success."""
    expected = NEXT_STEP.get(session["status"])
    if expected != step:
        raise ApiError(
            "STEP_OUT_OF_ORDER",
            409,
            details={
                "current_status": session["status"],
                "expected_step": expected,
                "attempted_step": step,
            },
        )


async def advance(
    db: AsyncDatabase,
    session: dict,
    step: str,
    step_data: dict[str, Any],
) -> dict:
    """Mark a step passed and move the session to the next state."""
    now = datetime.now(UTC)
    new_status = STEP_TO_STATE[step]
    payload = {f"steps.{step}.{k}": v for k, v in {**step_data, "status": "passed", "at": now}.items()}
    payload["status"] = new_status
    payload["updated_at"] = now

    updated = await db.verification_sessions.find_one_and_update(
        {"_id": session["_id"], "status": session["status"]},
        {"$set": payload},
        return_document=True,
    )
    if updated is None:
        raise ApiError("STEP_OUT_OF_ORDER", 409, details={"reason": "sesi berubah bersamaan"})
    return updated


async def record_failure(
    db: AsyncDatabase,
    session: dict,
    step: str,
    step_data: dict[str, Any],
    *,
    max_attempts: int,
    counter: str = "attempts",
) -> tuple[dict, int, bool]:
    """Increment a failure counter. Returns (session, count, exhausted)."""
    now = datetime.now(UTC)
    payload = {f"steps.{step}.{k}": v for k, v in {**step_data, "status": "failed", "at": now}.items()}
    payload["updated_at"] = now

    updated = await db.verification_sessions.find_one_and_update(
        {"_id": session["_id"]},
        {"$set": payload, "$inc": {f"steps.{step}.{counter}": 1}},
        return_document=True,
    )
    attempts = updated["steps"][step].get(counter, 1)
    exhausted = attempts >= max_attempts
    if exhausted:
        await db.verification_sessions.update_one(
            {"_id": session["_id"]},
            {
                "$set": {
                    "status": "rejected",
                    "updated_at": now,
                    "result": {
                        "decision": "REJECTED",
                        "reason_code": f"{step.upper()}_MAX_ATTEMPTS",
                        "reason_id": None,
                        "receipt_no": None,
                        "decided_at": now,
                    },
                }
            },
        )
    return updated, attempts, exhausted


async def cancel(db: AsyncDatabase, session: dict) -> None:
    if session["status"] in TERMINAL:
        return
    await db.verification_sessions.update_one(
        {"_id": session["_id"], "status": {"$nin": list(TERMINAL)}},
        {"$set": {"status": "cancelled", "updated_at": datetime.now(UTC)}},
    )


async def next_receipt_seq(db: AsyncDatabase) -> int:
    """Daily counter for human-readable receipt numbers (VRF-YYYYMMDD-NNNNNN)."""
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    count = await db.verification_sessions.count_documents(
        {"result.decided_at": {"$gte": start}, "result.receipt_no": {"$ne": None}}
    )
    return count + 1


def public_view(session: dict) -> dict:
    """What the client is allowed to see about its own session."""
    return {
        "session_id": str(session["_id"]),
        "status": session["status"],
        "current_step": NEXT_STEP.get(session["status"]),
        "required_steps": session.get("required_steps", REQUIRED_STEPS),
        "expires_at": session["expires_at"],
        "steps": {
            name: {k: v for k, v in data.items() if k not in {"template_id"}}
            for name, data in session.get("steps", {}).items()
        },
        "risk": session.get("risk", {}),
        "result": session.get("result"),
    }
