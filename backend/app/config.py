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

    mongo_uri: str = "mongodb://identicare:identicare@localhost:27017/?authSource=admin"
    mongo_db: str = "identicare"

    kek_path: Path = BACKEND_ROOT / "keys" / "kek.bin"
    rotation_path: Path = BACKEND_ROOT / "keys" / "rotation_v1.npy"
    nik_pepper: str = "dev-only-pepper-change-me"

    face_det_model: Path = BACKEND_ROOT / "models" / "det_500m.onnx"
    face_rec_model: Path = BACKEND_ROOT / "models" / "w600k_r50.onnx"
    face_embedding_dim: int = 512

    face_match_accept: float = 0.42
    face_match_review: float = 0.30
    face_collision_threshold: float = 0.55
    liveness_min_score: float = 0.70
    face_max_attempts: int = 3
    sessions_per_hour: int = 5
    face_max_quality_retries: int = 10

    enrollment_cooling_hours: int = 24
    enrollment_dedup_threshold: float = 0.45

    override_staff_weekly_limit: int = 5
    override_window_days: int = 7

    session_ttl_seconds: int = 600
    nonce_ttl_seconds: int = 120

    firebase_credentials: Path = BACKEND_ROOT / "keys" / "firebase-adminsdk.json"
    firebase_project_id: str = "identicare-591e3"
    facility_api_keys: str = ""
    operator_api_key: str = "dev-operator-key"

    ollama_url: str = "http://localhost:11434"
    cors_origins: str = "http://localhost,http://127.0.0.1"
    ort_intra_op_threads: int = 4

    @field_validator(
        "kek_path",
        "rotation_path",
        "face_det_model",
        "face_rec_model",
        "firebase_credentials",
        mode="after",
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
