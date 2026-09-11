"""Biometric matching: 1:1 verification and the 1:N collision sweep.

The asymmetry between these two is the whole point of the schema design:

  match_one  decrypts EXACTLY ONE template, compares, and wipes the buffer.
  sweep      decrypts NOTHING - it compares rotated search vectors, which carry
             identical cosine scores (see security/rotation.py).
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

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


class SearchBackend(Protocol):
    """Pluggable 1:N similarity search.

    Exists so the vector store can be swapped without touching callers. See
    docs/ARCHITECTURE.md section 3 for the scaling analysis: at 280 million
    participants a 512-d float32 index is roughly 573 GB and a Python scan is
    hopeless, so this moves to Qdrant. The 1:1 path is unaffected - it fetches
    exactly one document and decrypts it.

    The security property survives the move unchanged, which is the point of
    doing it this way: every implementation operates on ROTATED vectors (R.v).
    Cosine is invariant under a shared orthogonal rotation, so scores are
    identical while the store never holds a canonical ArcFace embedding. A
    breach of the vector index yields basis-scrambled numbers that no public
    face model can consume.
    """

    name: str

    async def upsert(
        self, *, template_id: Any, peserta_id: Any, rotated_vector: list[float]
    ) -> None: ...

    async def search(
        self,
        rotated_probe: np.ndarray,
        *,
        threshold: float,
        exclude_peserta_id: Any | None = None,
        limit: int = 5000,
    ) -> list[dict]: ...


class MongoScanBackend:
    """Brute-force cosine over `biometric_templates.search_vector`.

    Honest limits: fine to roughly 100k templates, minutes at 1M, impossible at
    BPJS scale. It is the default because it needs no extra infrastructure and
    is exactly right for a demo-sized dataset.
    """

    name = "mongo_scan"

    def __init__(self, db: AsyncDatabase, rot: np.ndarray) -> None:
        self._db = db
        self._rot = rot

    async def upsert(self, *, template_id, peserta_id, rotated_vector) -> None:
        # No-op: the vector already lives on the template document itself.
        return None

    async def search(
        self, rotated_probe, *, threshold, exclude_peserta_id=None, limit=5000
    ) -> list[dict]:
        return await _mongo_sweep(
            self._db,
            rotated_probe,
            threshold=threshold,
            exclude_peserta_id=exclude_peserta_id,
            limit=limit,
        )


def get_backend(db: AsyncDatabase, rot: np.ndarray, backend: str = "mongo_scan") -> SearchBackend:
    """Select the search backend. `qdrant` is designed but not yet built; see
    docs/ARCHITECTURE.md section 3."""
    if backend == "mongo_scan":
        return MongoScanBackend(db, rot)
    raise ValueError(
        f"unknown VECTOR_BACKEND={backend!r}. Only 'mongo_scan' is implemented; "
        "'qdrant' is designed in docs/ARCHITECTURE.md section 3."
    )


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
    rotated_probe = rotation.apply_rotation(rot, probe)
    return await _mongo_sweep(
        db,
        rotated_probe,
        threshold=threshold,
        exclude_peserta_id=exclude_peserta_id,
        limit=limit,
    )


async def _mongo_sweep(
    db: AsyncDatabase,
    rotated_probe: np.ndarray,
    *,
    threshold: float,
    exclude_peserta_id=None,
    limit: int = 5000,
) -> list[dict]:
    query: dict = {"modality": "face", "status": "active"}
    if exclude_peserta_id is not None:
        query["peserta_id"] = {"$ne": exclude_peserta_id}

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
