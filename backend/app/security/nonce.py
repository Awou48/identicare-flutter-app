"""Single-use nonces. This is the replay defence for the fingerprint step."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase


async def issue(
    db: AsyncDatabase, nonce: str, *, session_id: ObjectId, purpose: str, ttl_seconds: int
) -> None:
    now = datetime.now(UTC)
    await db.nonces.insert_one(
        {
            "_id": nonce,
            "session_id": session_id,
            "purpose": purpose,
            "used": False,
            "issued_at": now,
            "expires_at": now + timedelta(seconds=ttl_seconds),
        }
    )


async def consume(db: AsyncDatabase, nonce: str, *, session_id: ObjectId) -> str | None:
    """Atomically mark a nonce used. Returns an error code, or None on success.

    The atomicity is the whole point. `_id` is the nonce itself and is unique, so
    findOneAndUpdate({_id, used: False}) either wins or returns null - two
    parallel requests replaying the same signature cannot both succeed. A
    read-then-write would race.
    """
    doc = await db.nonces.find_one_and_update(
        {"_id": nonce, "session_id": session_id, "used": False},
        {"$set": {"used": True, "used_at": datetime.now(UTC)}},
        return_document=False,
    )
    if doc is None:
        # Distinguish "already used" from "never existed / TTL-expired" so the UI
        # can say something specific.
        existing = await db.nonces.find_one({"_id": nonce})
        if existing is None:
            return "NONCE_EXPIRED"
        return "NONCE_REUSED"

    expires_at = doc["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if datetime.now(UTC) > expires_at:
        return "NONCE_EXPIRED"
    return None
