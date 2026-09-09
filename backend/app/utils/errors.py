"""Shared error envelope.

Two categories, deliberately distinguished:

  * ApiError  -> a PROTOCOL error. 4xx/5xx. The client did something wrong or the
                 session is in the wrong state.
  * StepFailure -> a BUSINESS outcome. Always HTTP 200 with result="failed".

The second one matters. A face mismatch is not an error - it is the system
working correctly and rejecting an impostor, and the UI has to render it with a
score and a retry count. If it came back as 4xx it would be swallowed by generic
"something went wrong" handling in Flutter, and the user would never learn why.
"""

from __future__ import annotations

from typing import Any

# Indonesian messages - all user-facing copy in this app is Indonesian.
MESSAGES: dict[str, str] = {
    # session / protocol
    "PESERTA_NOT_FOUND": "Data peserta tidak ditemukan.",
    "BIOMETRIC_NOT_ENROLLED": "Peserta belum melakukan pendaftaran biometrik.",
    "PESERTA_NONAKTIF": "Kepesertaan BPJS tidak aktif.",
    "SESSION_NOT_FOUND": "Sesi verifikasi tidak ditemukan.",
    "SESSION_EXPIRED": "Sesi verifikasi telah kedaluwarsa. Silakan ulangi dari awal.",
    "SESSION_CLOSED": "Sesi verifikasi sudah selesai atau dibatalkan.",
    "STEP_OUT_OF_ORDER": "Langkah verifikasi tidak berurutan.",
    "INVALID_SESSION_TOKEN": "Token sesi tidak valid.",
    "UNAUTHENTICATED": "Autentikasi diperlukan.",
    "FORBIDDEN": "Anda tidak berhak mengakses data ini.",
    "INVALID_API_KEY": "API key fasilitas kesehatan tidak valid.",
    "FASKES_NOT_FOUND": "Fasilitas kesehatan tidak ditemukan.",
    "DEVICE_BLOCKED": "Perangkat ini diblokir karena aktivitas mencurigakan.",
    "DEVICE_NOT_ENROLLED": "Perangkat belum terdaftar.",
    "TOO_MANY_SESSIONS": "Terlalu banyak sesi verifikasi. Coba lagi nanti.",
    "MAX_ATTEMPTS": "Batas percobaan tercapai. Sesi ditolak.",
    "IMAGE_TOO_LARGE": "Ukuran gambar melebihi batas 5 MB.",
    "NO_FRAMES": "Tidak ada gambar yang dikirim.",
    "MODEL_UNAVAILABLE": "Model pengenalan wajah belum tersedia di server.",
    "ALREADY_ENROLLED": "Peserta sudah memiliki data biometrik aktif.",
    "VALIDATION_ERROR": "Data yang dikirim tidak valid.",
    "INTERNAL_ERROR": "Terjadi kesalahan pada server.",
    # face step outcomes
    "FACE_MISMATCH": "Wajah tidak cocok dengan data peserta.",
    "NO_FACE_DETECTED": "Wajah tidak terdeteksi. Pastikan wajah terlihat jelas.",
    "MULTIPLE_FACES": "Terdeteksi lebih dari satu wajah. Pastikan hanya Anda di depan kamera.",
    "LOW_QUALITY_BLUR": "Gambar terlalu buram. Tahan ponsel lebih stabil.",
    "LOW_QUALITY_LIGHT": "Pencahayaan kurang memadai.",
    "FACE_TOO_SMALL": "Wajah terlalu jauh. Dekatkan wajah ke kamera.",
    "LIVENESS_FAILED": "Deteksi keaslian gagal. Ikuti instruksi yang ditampilkan.",
    "SPOOF_SUSPECTED": "Terdeteksi indikasi pemalsuan wajah.",
    "ENROLL_FRAMES_INCONSISTENT": "Gambar pendaftaran tidak konsisten. Ulangi pengambilan.",
    # fingerprint step outcomes
    "SIGNATURE_INVALID": "Tanda tangan sidik jari tidak valid.",
    "NONCE_REUSED": "Kode verifikasi sudah digunakan.",
    "NONCE_EXPIRED": "Kode verifikasi kedaluwarsa.",
    "KEY_MISMATCH": "Kunci perangkat tidak cocok dengan yang terdaftar.",
    "BIOMETRIC_CANCELLED": "Verifikasi sidik jari dibatalkan.",
    "NO_BIOMETRIC_HARDWARE": "Perangkat tidak memiliki sensor sidik jari.",
    "ATTESTATION_FAILED": "Attestation perangkat tidak dapat diverifikasi.",
    # review / commit
    "REVIEW_NOT_CONFIRMED": "Data belum dikonfirmasi.",
    "STEPS_INCOMPLETE": "Ada langkah verifikasi yang belum selesai.",
}


def message_for(code: str, fallback: str | None = None) -> str:
    return MESSAGES.get(code, fallback or MESSAGES["INTERNAL_ERROR"])


class ApiError(Exception):
    """A protocol-level failure. Rendered as the shared envelope with a 4xx/5xx."""

    def __init__(
        self,
        code: str,
        status_code: int = 400,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.status_code = status_code
        self.message = message or message_for(code)
        self.details = details or {}
        super().__init__(f"{code}: {self.message}")


def error_body(code: str, message: str, request_id: str, details: dict | None = None) -> dict:
    body = {
        "status": "error",
        "error_code": code,
        "message": message,
        "request_id": request_id,
    }
    if details:
        body["details"] = details
    return body


# --------------------------------------------------------------------------- #
# Log redaction
# --------------------------------------------------------------------------- #
REDACT_KEYS = {
    "nik",
    "nik_enc",
    "ciphertext",
    "dek_wrapped",
    "search_vector",
    "embedding",
    "signature_b64",
    "signed_payload_b64",
    "public_key_der",
    "nonce",
    "session_token",
    "password",
    "authorization",
}


def redact(payload: Any) -> Any:
    """Strip biometric and secret material before anything reaches a log.

    Embeddings, NIKs, nonces and signatures must never be written to disk in the
    clear - a log file is the one place people forget to protect.
    """
    if isinstance(payload, dict):
        return {
            k: ("<redacted>" if k.lower() in REDACT_KEYS else redact(v))
            for k, v in payload.items()
        }
    if isinstance(payload, list):
        return [redact(v) for v in payload[:20]]
    if isinstance(payload, bytes):
        return f"<{len(payload)} bytes>"
    return payload
