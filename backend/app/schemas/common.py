from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    status: Literal["error"] = "error"
    error_code: str
    message: str
    request_id: str
    details: dict[str, Any] | None = None


class OkResponse(BaseModel):
    status: Literal["ok"] = "ok"


class StepResponse(OkResponse):
    """Business outcome for one flow step."""

    step: str
    result: Literal["passed", "failed"]
    error_code: str | None = None
    message: str | None = None
    next_step: str | None = None
    attempts_used: int | None = None
    attempts_left: int | None = None


class DeviceInfo(BaseModel):
    device_uid: str = Field(min_length=16, max_length=128)
    platform: str = "android"
    os_version: str | None = None
    model: str | None = None
    app_version: str | None = None


class GeoPoint(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: list[float] = Field(min_length=2, max_length=2)


class RiskAssessment(BaseModel):
    score: int = 0
    band: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"
    signals: list[dict[str, Any]] = Field(default_factory=list)
    evaluated_at: datetime | None = None
