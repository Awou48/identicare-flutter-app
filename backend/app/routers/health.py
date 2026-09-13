from __future__ import annotations

from fastapi import APIRouter

from app import db as database
from app.deps import SettingsDep
from app.security import firebase_auth
from app.services import face_engine

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(settings: SettingsDep) -> dict:
    checks: dict = {"env": settings.identicare_env}

    try:
        db = database.get_db()
        await db.command("ping")
        checks["mongo"] = "ok"
        checks["peserta_count"] = await db.peserta.count_documents({})
        checks["enrolled_templates"] = await db.biometric_templates.count_documents(
            {"modality": "face", "status": "active"}
        )
    except Exception as exc:
        checks["mongo"] = f"error: {type(exc).__name__}"

    engine = face_engine.get_engine()
    if engine is not None:
        checks["face_models"] = "loaded"
        checks["embedding_dim"] = engine.embedding_dim
    else:
        checks["face_models"] = "unavailable"
        checks["face_models_error"] = face_engine.load_error()

    checks["firebase_auth"] = firebase_auth.status()
    checks["keys_loaded"] = database.is_connected()
    checks["thresholds"] = {
        "face_accept": settings.face_match_accept,
        "face_review": settings.face_match_review,
        "liveness_min": settings.liveness_min_score,
    }

    healthy = checks.get("mongo") == "ok"
    return {"status": "ok" if healthy else "degraded", "checks": checks}
