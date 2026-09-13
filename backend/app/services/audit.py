from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

log = logging.getLogger(__name__)


async def record(
    db: AsyncDatabase,
    *,
    who: str,
    what: str,
    peserta_id: ObjectId | None = None,
    session_id: ObjectId | None = None,
    purpose: str = "",
) -> None:
    await db.audit_log.insert_one(
        {
            "who": who,
            "what": what,
            "peserta_id": peserta_id,
            "session_id": session_id,
            "purpose": purpose,
            "at": datetime.now(UTC),
        }
    )


async def log_event(
    db: AsyncDatabase,
    *,
    session_id: ObjectId,
    step: str,
    outcome: str,
    peserta_id: ObjectId | None = None,
    method: str = "",
    scores: dict[str, Any] | None = None,
    error_code: str | None = None,
    device_uid: str | None = None,
    faskes_id: ObjectId | None = None,
    geo: dict | None = None,
    latency_ms: float | None = None,
    request_id: str | None = None,
) -> int:
    """Append one event. Failures are logged too - a failed face scan is exactly the signal the fraud engine
    wants, and `session.steps` only keeps the last attempt.
    """
    for _ in range(3):
        seq = await db.verification_events.count_documents({"session_id": session_id})
        doc = {
            "session_id": session_id,
            "peserta_id": peserta_id,
            "seq": seq,
            "step": step,
            "outcome": outcome,
            "method": method,
            "scores": scores or {},
            "error_code": error_code,
            "device_uid": device_uid,
            "faskes_id": faskes_id,
            "latency_ms": latency_ms,
            "request_id": request_id,
            "at": datetime.now(UTC),
        }
        if geo:
            doc["geo"] = geo
        try:
            await db.verification_events.insert_one(doc)
            return seq
        except DuplicateKeyError:
            continue
    log.warning("could not append event for session %s step %s", session_id, step)
    return -1
