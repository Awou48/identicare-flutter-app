from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.routers import face as face_router
from app.utils import images

OBSERVED_PHONE_BLUR_VARS = [19.1, 38.0, 43.0, 69.7, 75.9]


def _frame_with_variance(target: float, size=(480, 640)) -> np.ndarray:
    """A mostly-flat grey frame with just enough noise to hit a given Laplacian variance - what a selfie
    against a wall looks like to the gate.
    """
    rng = np.random.default_rng(0)
    lo, hi = 0.0, 40.0
    for _ in range(40):
        sigma = (lo + hi) / 2
        img = np.clip(115 + rng.normal(0, sigma, size), 0, 255).astype(np.uint8)
        bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        v = images.blur_variance(bgr)
        if abs(v - target) < 1.0:
            return bgr
        lo, hi = (sigma, hi) if v < target else (lo, sigma)
    return bgr


@pytest.mark.parametrize("blur_var", OBSERVED_PHONE_BLUR_VARS)
def test_real_phone_frames_pass_the_whole_frame_gate(blur_var: float) -> None:
    frame = _frame_with_variance(blur_var)
    code, measured, bright = images.quality_gate(frame)
    assert abs(measured - blur_var) < 1.5
    assert code is None, f"a frame the phone produced in good light was rejected: {code}"


def test_a_covered_lens_still_fails() -> None:
    flat = np.full((480, 640, 3), 115, dtype=np.uint8)
    code, _, _ = images.quality_gate(flat)
    assert code == "LOW_QUALITY_BLUR"


def test_dark_and_blown_out_frames_still_fail() -> None:
    rng = np.random.default_rng(1)
    dark = np.clip(20 + rng.normal(0, 10, (480, 640)), 0, 255).astype(np.uint8)
    blown = np.clip(240 + rng.normal(0, 10, (480, 640)), 0, 255).astype(np.uint8)
    for arr in (dark, blown):
        code, _, _ = images.quality_gate(cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR))
        assert code == "LOW_QUALITY_LIGHT"


def test_face_crop_sharpness_is_the_real_sharpness_check() -> None:
    """A sharp face on a flat wall: the whole frame measures low, the crop measures high. The gate must judge
    the crop.
    """
    rng = np.random.default_rng(2)
    frame = np.full((480, 640, 3), 115, dtype=np.uint8)
    face = np.clip(120 + rng.normal(0, 30, (200, 160, 3)), 0, 255).astype(np.uint8)
    frame[140:340, 240:400] = face
    whole = images.blur_variance(frame)
    crop = images.region_sharpness(frame, np.array([240, 140, 400, 340]))
    assert crop > images.MIN_FACE_SHARPNESS
    assert crop > whole * 3

    blurred = frame.copy()
    blurred[140:340, 240:400] = cv2.GaussianBlur(face, (31, 31), 8)
    assert images.region_sharpness(blurred, np.array([240, 140, 400, 340])) < images.MIN_FACE_SHARPNESS


def test_quality_failures_are_not_identity_failures() -> None:
    """The codes that get the separate, larger budget are exactly the ones that carry no information about who
    is in front of the camera.
    """
    assert face_router.QUALITY_CODES == {
        "LOW_QUALITY_BLUR",
        "LOW_QUALITY_LIGHT",
        "NO_FACE_DETECTED",
        "FACE_TOO_SMALL",
        "MULTIPLE_FACES",
    }
    for identity_code in ("FACE_MISMATCH", "LIVENESS_FAILED", "SPOOF_SUSPECTED"):
        assert identity_code not in face_router.QUALITY_CODES


def test_quality_retries_do_not_consume_identity_attempts() -> None:
    """Live-DB check of the two budgets. Ten blurry frames must leave the three identity attempts untouched
    and the session open.
    """
    import asyncio
    from datetime import UTC, datetime, timedelta

    from bson import ObjectId
    from pymongo import AsyncMongoClient, MongoClient
    from pymongo.errors import ServerSelectionTimeoutError

    from app.config import get_settings
    from app.services import session_service

    settings = get_settings()
    sync = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=1500)
    try:
        sync.admin.command("ping")
    except ServerSelectionTimeoutError:
        pytest.skip("MongoDB not reachable")

    now = datetime.now(UTC)
    sid = (
        sync[settings.mongo_db]
        .verification_sessions.insert_one(
            {
                "session_token": "test-token-quality-budget-" + "x" * 32,
                "status": "created",
                "peserta_id": ObjectId(),
                "steps": {},
                "created_at": now,
                "updated_at": now,
                "expires_at": now + timedelta(minutes=10),
                "_test": True,
            }
        )
        .inserted_id
    )

    async def run():
        client = AsyncMongoClient(settings.mongo_uri)
        db = client[settings.mongo_db]
        try:
            session = await db.verification_sessions.find_one({"_id": sid})
            for _ in range(settings.face_max_quality_retries - 1):
                updated, n, exhausted = await session_service.record_failure(
                    db,
                    session,
                    "face",
                    {"error_code": "LOW_QUALITY_BLUR"},
                    max_attempts=settings.face_max_quality_retries,
                    counter="quality_retries",
                )
                assert not exhausted
            assert updated["steps"]["face"].get("attempts", 0) == 0
            assert updated["steps"]["face"]["quality_retries"] == settings.face_max_quality_retries - 1
            assert updated["status"] == "created"

            updated, n, exhausted = await session_service.record_failure(
                db,
                session,
                "face",
                {"error_code": "FACE_MISMATCH"},
                max_attempts=settings.face_max_attempts,
            )
            assert (n, exhausted) == (1, False)
            assert updated["steps"]["face"]["quality_retries"] == settings.face_max_quality_retries - 1
        finally:
            await client.close()

    try:
        asyncio.new_event_loop().run_until_complete(run())
    finally:
        sync[settings.mongo_db].verification_sessions.delete_one({"_id": sid})
        sync.close()
