"""Application settings, loaded from backend/.env via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    identicare_env: str = "dev"

    # --- MongoDB ---
    mongo_uri: str = "mongodb://identicare:identicare@localhost:27017/?authSource=admin"
    mongo_db: str = "identicare"

    # --- Key material ---
    kek_path: Path = BACKEND_ROOT / "keys" / "kek.bin"
    rotation_path: Path = BACKEND_ROOT / "keys" / "rotation_v1.npy"
    nik_pepper: str = "dev-only-pepper-change-me"

    # --- Face models ---
    face_det_model: Path = BACKEND_ROOT / "models" / "det_500m.onnx"
    face_rec_model: Path = BACKEND_ROOT / "models" / "w600k_r50.onnx"
    face_embedding_dim: int = 512

    # --- Thresholds ---
    face_match_accept: float = 0.42
    face_match_review: float = 0.30
    face_collision_threshold: float = 0.55
    liveness_min_score: float = 0.70
    face_max_attempts: int = 3

    # --- Enrolment identity proofing --- #
    # A template younger than this cannot underwrite a high-value claim. Bounds
    # the damage from an enrolment that was fraudulent but not yet detected.
    enrollment_cooling_hours: int = 24
    # Enrolment de-duplication is deliberately STRICTER than the in-claim
    # collision threshold: a false reject at enrolment costs one retry, a false
    # accept creates a permanently poisoned identity.
    enrollment_dedup_threshold: float = 0.45

    # --- Staff override --- #
    # Overrides per staff member over a rolling week before the frequency rule
    # escalates to critical. A nurse overriding twenty times a day IS the fraud.
    override_staff_weekly_limit: int = 5
    override_window_days: int = 7

    # --- Sessions ---
    session_ttl_seconds: int = 600
    nonce_ttl_seconds: int = 120

    # --- Auth ---
    firebase_credentials: Path = BACKEND_ROOT / "keys" / "firebase-adminsdk.json"
    facility_api_keys: str = ""
    operator_api_key: str = "dev-operator-key"

    # --- Misc ---
    ollama_url: str = "http://localhost:11434"
    cors_origins: str = "http://localhost,http://127.0.0.1"
    ort_intra_op_threads: int = 4

    # .env carries relative paths like "./models/det_500m.onnx". Those resolve
    # against the CWD, which differs between `python scripts/x.py` (backend/) and
    # `uvicorn --app-dir backend` (repo root) - so the same config silently found
    # the models in one case and not the other. Anchor every path to backend/.
    @field_validator(
        "kek_path", "rotation_path", "face_det_model", "face_rec_model",
        "firebase_credentials", mode="after",
    )
    @classmethod
    def _resolve_against_backend(cls, value: Path) -> Path:
        value = Path(value)
        return value if value.is_absolute() else (BACKEND_ROOT / value).resolve()

    @property
    def kek_file(self) -> Path:
        return self.kek_path

    @property
    def rotation_file(self) -> Path:
        return self.rotation_path

    @property
    def facility_key_map(self) -> dict[str, str]:
        """Parse "kode:key,kode:key" into {api_key: kode_faskes}."""
        out: dict[str, str] = {}
        for pair in self.facility_api_keys.split(","):
            pair = pair.strip()
            if not pair or ":" not in pair:
                continue
            kode, key = pair.split(":", 1)
            out[key.strip()] = kode.strip()
        return out


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
