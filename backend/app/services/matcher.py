from __future__ import annotations

import logging
from typing import Any, Protocol

import numpy as np
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase

from app.security import crypto, rotation
from app.services import audit

log = logging.getLogger(__name__)


PLACEHOLDER_MODEL_PREFIX = "PLACEHOLDER"
REAL_TEMPLATE_FILTER = {"model.name": {"$not": {"$regex": f"^{PLACEHOLDER_MODEL_PREFIX}"}}}


def is_placeholder(template: dict | None) -> bool:
    return bool(template) and str((template.get("model") or {}).get("name", "")).startswith(
        PLACEHOLDER_MODEL_PREFIX
    )


async def get_active_template(db: AsyncDatabase, peserta_id: ObjectId) -> dict | None:
    """The participant's live face template, or None. Placeholders are None."""
    return await db.biometric_templates.find_one(
        {"peserta_id": peserta_id, "modality": "face", "status": "active", **REAL_TEMPLATE_FILTER}
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
    """1:1 cosine against a single enrolled template."""
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
    """Pluggable 1:N similarity search."""

    name: str

    async def upsert(self, *, template_id: Any, peserta_id: Any, rotated_vector: list[float]) -> None: ...

    async def search(
        self,
        rotated_probe: np.ndarray,
        *,
        threshold: float,
        exclude_peserta_id: Any | None = None,
        limit: int = 5000,
    ) -> list[dict]: ...


class MongoScanBackend:
    """Brute-force cosine over `biometric_templates.search_vector`."""

    name = "mongo_scan"

    def __init__(self, db: AsyncDatabase, rot: np.ndarray) -> None:
        self._db = db
        self._rot = rot

    async def upsert(self, *, template_id, peserta_id, rotated_vector) -> None:
        return None

    async def search(self, rotated_probe, *, threshold, exclude_peserta_id=None, limit=5000) -> list[dict]:
        return await _mongo_sweep(
            self._db,
            rotated_probe,
            threshold=threshold,
            exclude_peserta_id=exclude_peserta_id,
            limit=limit,
        )


def get_backend(db: AsyncDatabase, rot: np.ndarray, backend: str = "mongo_scan") -> SearchBackend:
    """Select the search backend. `qdrant` is designed but not yet built (docs/ARCHITECTURE.md §3)."""
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
    """1:N: is this face already enrolled under a different peserta?"""
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
    query: dict = {"modality": "face", "status": "active", **REAL_TEMPLATE_FILTER}
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
    """accept | review | reject."""
    if score >= accept:
        return "accept"
    if score >= review:
        return "review"
    return "reject"
