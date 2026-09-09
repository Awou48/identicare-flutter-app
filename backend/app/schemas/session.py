"""Verification session and step payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import DeviceInfo, OkResponse, StepResponse
from app.schemas.peserta import PesertaFull, PesertaPreview


class ClaimInfo(BaseModel):
    claim_ref: str | None = None
    jenis_layanan: Literal["RAWAT_JALAN", "RAWAT_INAP", "IGD", "FARMASI"] = "RAWAT_JALAN"
    poli: str = ""
    estimasi_biaya: int = Field(default=0, ge=0)


class SessionCreate(BaseModel):
    no_bpjs: str = Field(pattern=r"^[0-9]{13}$")
    kode_faskes: str
    claim: ClaimInfo = Field(default_factory=ClaimInfo)
    device: DeviceInfo


class SessionCreated(OkResponse):
    session_id: str
    session_token: str
    expires_at: datetime
    required_steps: list[str]
    current_step: str | None
    nonce: str
    nonce_expires_at: datetime
    peserta_preview: PesertaPreview


class SessionState(OkResponse):
    session_id: str
    status: str
    current_step: str | None
    required_steps: list[str]
    expires_at: datetime
    steps: dict[str, Any]
    risk: dict[str, Any]
    result: dict[str, Any] | None


class LivenessChallenge(OkResponse):
    challenge_id: str
    challenge: str
    instruction: str
    expires_at: datetime


class FaceQuality(BaseModel):
    blur_var: float = 0.0
    brightness: float = 0.0
    face_px: int = 0
    det_score: float = 0.0


class LivenessInfo(BaseModel):
    passed: bool
    score: float
    method: str
    signals: dict[str, float] = Field(default_factory=dict)
    reason: str | None = None


class FaceStepResponse(StepResponse):
    step: Literal["face"] = "face"
    match_score: float | None = None
    threshold: float | None = None
    liveness: LivenessInfo | None = None
    quality: FaceQuality | None = None
    latency_ms: int | None = None
    nonce: str | None = None


class FingerprintSubmit(BaseModel):
    method: str = Field(description="hmac_sha256_shared_secret | android_keystore_ec_p256")
    key_alias: str | None = None
    nonce: str
    timestamp: int
    signature_b64: str
    device_uid: str
    biometric_type: str = "fingerprint"


class FingerprintStepResponse(StepResponse):
    step: Literal["fingerprint"] = "fingerprint"
    signature_verified: bool = False
    security_level: str | None = None
    user_auth_required: bool | None = None


class ReviewClaim(BaseModel):
    claim_ref: str | None = None
    jenis_layanan: str
    poli: str
    estimasi_biaya: int
    faskes: str


class BiometrikSummary(BaseModel):
    wajah: dict[str, Any]
    sidik_jari: dict[str, Any]


class ReviewData(OkResponse):
    peserta: PesertaFull
    claim: ReviewClaim
    biometrik: BiometrikSummary
    risk: dict[str, Any]


class ReviewConfirm(BaseModel):
    confirmed: bool
    corrections: dict[str, Any] = Field(default_factory=dict)


class CommitRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=64)


class CommitResponse(OkResponse):
    decision: Literal["APPROVED", "REVIEW", "REJECTED"]
    receipt_no: str | None
    decided_at: datetime
    risk: dict[str, Any]
    summary: dict[str, Any]


class HistoryItem(BaseModel):
    session_id: str
    receipt_no: str | None
    tanggal: datetime
    metode: list[str]
    status: str
    lokasi: dict[str, Any]
    skor: dict[str, Any]
    risk_band: str


class HistoryPage(OkResponse):
    items: list[HistoryItem]
    next_cursor: str | None = None
    has_more: bool = False
