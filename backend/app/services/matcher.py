"""Biometric matching: 1:1 verification and the 1:N collision sweep.

The asymmetry between these two is the whole point of the schema design:

  match_one  decrypts EXACTLY ONE template, compares, and wipes the buffer.
  sweep      decrypts NOTHING - it compares rotated search vectors, which carry
             identical cosine scores (see security/rotation.py).
"""

from __future__ import annotations

import logging

import numpy as np
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase

from app.security import crypto, rotation
from app.services import audit

log = logging.getLogger(__name__)


async def get_active_template(db: AsyncDatabase, peserta_id: ObjectId) -> dict | None:
    return await db.biometric_templates.find_one(
        {"peserta_id": peserta_id, "modality": "face", "status": "active"}
    )


async def match_one(
    db: AsyncDatabase,
    kek: bytes,
    template: dict,
    probe: np.ndarray,
    *,
    actor: str,
    session_id: ObjectId | None = None,
    dim: int = 512,
) -> float:
    """1:1 cosine against a single enrolled template.

    Decrypts into process memory, compares, then zeroes the buffer. Every
    decryption is written to audit_log - without that record, "we protect
    biometric data" is an unverifiable claim.
    """
    aad = crypto.build_aad(template["peserta_id"], template["_id"], template.get("version", 1))
    enrolled = crypto.decrypt_embedding(kek, template["enc"], aad, dim=dim)
    try:
        score = rotation.cosine(enrolled, probe)
    finally:
        crypto.wipe(enrolled)

    await audit.record(
        db,
        who=actor,
        what="decrypt_face_template",
        peserta_id=template["peserta_id"],
        session_id=session_id,
        purpose="verifikasi_1_1",
    )
    return score


async def sweep_collisions(
    db: AsyncDatabase,
    rot: np.ndarray,
    probe: np.ndarray,
    *,
    threshold: float,
    exclude_peserta_id: ObjectId | None = None,
    limit: int = 5000,
) -> list[dict]:
    """1:N: is this face already enrolled under a different peserta?

    Runs entirely on `search_vector`, so nothing is decrypted and nothing is
    written to audit_log - there is no plaintext biometric access to record.
    """
    query: dict = {"modality": "face", "status": "active"}
    if exclude_peserta_id is not None:
        query["peserta_id"] = {"$ne": exclude_peserta_id}

    rotated_probe = rotation.apply_rotation(rot, probe)

    cursor = db.biometric_templates.find(
        query, {"peserta_id": 1, "search_vector": 1, "rotation_id": 1}
    ).limit(limit)

    hits: list[dict] = []
    async for doc in cursor:
        vec = doc.get("search_vector")
        if not vec:
            continue
        if doc.get("rotation_id") != rotation.ROTATION_ID:
            # A template rotated with a retired matrix cannot be compared against
            # the current one. Skip rather than produce a meaningless score.
            log.warning(
                "template %s uses rotation %s, expected %s - skipped in sweep",
                doc["_id"],
                doc.get("rotation_id"),
                rotation.ROTATION_ID,
            )
            continue
        score = rotation.cosine(np.asarray(vec, dtype=np.float32), rotated_probe)
        if score >= threshold:
            hits.append(
                {"peserta_id": doc["peserta_id"], "template_id": doc["_id"], "score": round(score, 4)}
            )

    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits


def decide(score: float, accept: float, review: float) -> str:
    """accept | review | reject.

    Thresholds are stricter than InsightFace's own 0.28 demo default because the
    cost here is asymmetric: a false accept is a fraudulent BPJS claim, while a
    false reject costs one retry out of three.
    """
    if score >= accept:
        return "accept"
    if score >= review:
        return "review"
    return "reject"
