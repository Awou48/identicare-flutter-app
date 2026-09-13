from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import WriteError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import db as database
from app.config import get_settings
from app.routers import (
    articles,
    enrollment,
    face,
    fingerprint,
    fraud,
    health,
    override,
    peserta,
    sessions,
    staff,
    symptoms,
)
from app.routers import history as history_router
from app.security import firebase_auth
from app.services import face_engine
from app.utils.errors import ApiError, error_body, message_for

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
log = logging.getLogger("identicare")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    log.info("Starting IdentiCare API (env=%s)", settings.identicare_env)

    await database.connect(settings)
    log.info("MongoDB connected: %s", settings.mongo_db)

    firebase_auth.init(settings)

    started = time.perf_counter()
    engine = face_engine.load_engine(
        settings.face_det_model, settings.face_rec_model, settings.ort_intra_op_threads
    )
    if engine:
        log.info(
            "Face models loaded in %.1fs (dim=%d)",
            time.perf_counter() - started,
            engine.embedding_dim,
        )
    else:
        log.warning("Face models unavailable: %s", face_engine.load_error())

    yield

    await database.disconnect()
    log.info("Shutdown complete")


app = FastAPI(
    title="IdentiCare API",
    description=(
        "Verifikasi biometrik klaim BPJS: pengenalan wajah, deteksi keaslian (liveness), "
        "dan sidik jari perangkat, dengan deteksi fraud berbasis aturan."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()
    response = await call_next(request)
    elapsed = (time.perf_counter() - started) * 1000
    response.headers["X-Request-Id"] = request.state.request_id
    if not request.url.path.startswith(("/docs", "/openapi", "/redoc")):
        log.info(
            "%s %s -> %s (%.0f ms) [%s]",
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
            request.state.request_id,
        )
    return response


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message, _request_id(request), exc.details),
    )


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_body(
            "VALIDATION_ERROR",
            message_for("VALIDATION_ERROR"),
            _request_id(request),
            {"errors": exc.errors()[:5]},
        ),
    )


@app.exception_handler(StarletteHTTPException)
async def http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body("HTTP_ERROR", str(exc.detail), _request_id(request), {"status": exc.status_code}),
    )


@app.exception_handler(WriteError)
async def write_error_handler(request: Request, exc: WriteError) -> JSONResponse:
    """A MongoDB validator rejection is a contract bug, not a server fault."""
    fields: list[str] = []
    try:
        details = (exc.details or {}).get("errInfo", {}).get("details", {})
        for rule in details.get("schemaRulesNotSatisfied", []):
            for prop in rule.get("propertiesNotSatisfied", []):
                fields.append(prop.get("propertyName"))
    except (AttributeError, TypeError):
        pass
    log.error("Document validation failed on %s: fields=%s", request.url.path, fields)
    return JSONResponse(
        status_code=422,
        content=error_body(
            "VALIDATION_ERROR",
            message_for("VALIDATION_ERROR"),
            _request_id(request),
            {"invalid_fields": fields} if fields else None,
        ),
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled error on %s [%s]", request.url.path, _request_id(request))
    return JSONResponse(
        status_code=500,
        content=error_body("INTERNAL_ERROR", message_for("INTERNAL_ERROR"), _request_id(request)),
    )


API_PREFIX = "/api/v1"
app.include_router(health.router, prefix=API_PREFIX)
app.include_router(enrollment.router, prefix=API_PREFIX)
app.include_router(sessions.router, prefix=API_PREFIX)
app.include_router(face.router, prefix=API_PREFIX)
app.include_router(fingerprint.router, prefix=API_PREFIX)
app.include_router(override.router, prefix=API_PREFIX)
app.include_router(staff.router, prefix=API_PREFIX)
app.include_router(history_router.router, prefix=API_PREFIX)
app.include_router(fraud.router, prefix=API_PREFIX)
app.include_router(articles.router, prefix=API_PREFIX)
app.include_router(peserta.router, prefix=API_PREFIX)
app.include_router(symptoms.router)


@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {
        "name": "IdentiCare API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": f"{API_PREFIX}/health",
    }
