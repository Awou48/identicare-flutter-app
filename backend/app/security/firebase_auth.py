from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import jwt
from cryptography.x509 import load_pem_x509_certificate

from app.config import Settings
from app.utils.errors import ApiError

log = logging.getLogger(__name__)

GOOGLE_CERTS_URL = "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"

LEEWAY_SECONDS = 60

_initialised = False
_admin_available = False
_public_key_available = False

_cert_cache: dict[str, object] = {}
_cert_expiry: float = 0.0
_cert_lock = threading.Lock()


@dataclass
class CurrentUser:
    uid: str
    email: str | None = None
    dev_mode: bool = False

    method: str = "unknown"


def init(settings: Settings) -> bool:
    """Decide which verification paths are available. Never raises."""
    global _initialised, _admin_available, _public_key_available
    if _initialised:
        return _admin_available or _public_key_available
    _initialised = True

    cred_path = Path(settings.firebase_credentials)
    if not cred_path.is_absolute():
        from app.config import BACKEND_ROOT

        cred_path = BACKEND_ROOT / cred_path

    if cred_path.exists():
        try:
            import firebase_admin
            from firebase_admin import credentials

            if not firebase_admin._apps:
                firebase_admin.initialize_app(credentials.Certificate(str(cred_path)))
            _admin_available = True
            log.info("Firebase Admin initialised from %s", cred_path)
        except Exception:
            log.exception("Failed to initialise Firebase Admin; falling back to public keys")

    if settings.firebase_project_id:
        _public_key_available = True
        if not _admin_available:
            log.info(
                "Verifying Firebase ID tokens against Google public keys for project %s "
                "(no service account needed).",
                settings.firebase_project_id,
            )
    else:
        log.error(
            "FIREBASE_PROJECT_ID is not set, so ID tokens cannot be verified. "
            "Set it to the project id from lib/firebase_options.dart."
        )

    if not (_admin_available or _public_key_available) and settings.identicare_env == "dev":
        log.warning(
            "No Firebase verification available. DEV MODE: accepting "
            "'Authorization: Bearer dev:<uid>'. Never deploy like this."
        )

    return _admin_available or _public_key_available


def is_available() -> bool:
    return _admin_available or _public_key_available


def status() -> str:
    """Human-readable mode, for /health."""
    if _admin_available:
        return "admin-sdk"
    if _public_key_available:
        return "google-public-keys"
    return "dev-bypass"


def _fetch_certs() -> dict[str, object]:
    """Google's signing certificates, cached until Cache-Control says otherwise."""
    global _cert_expiry

    with _cert_lock:
        if _cert_cache and time.time() < _cert_expiry:
            return _cert_cache

        try:
            response = httpx.get(GOOGLE_CERTS_URL, timeout=10.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            if _cert_cache:
                log.warning("Could not refresh Google certs (%s); using cached keys", exc)
                return _cert_cache
            raise ApiError(
                "UNAUTHENTICATED",
                503,
                message="Tidak dapat memverifikasi token: kunci publik Google tidak terjangkau.",
            ) from exc

        certs: dict[str, object] = {}
        for kid, pem in response.json().items():
            try:
                certs[kid] = load_pem_x509_certificate(pem.encode()).public_key()
            except Exception:
                log.warning("Skipping unparseable certificate %s", kid)

        max_age = 3600
        cache_control = response.headers.get("cache-control", "")
        for part in cache_control.split(","):
            part = part.strip()
            if part.startswith("max-age="):
                try:
                    max_age = int(part.split("=", 1)[1])
                except ValueError:
                    pass

        _cert_cache.clear()
        _cert_cache.update(certs)
        _cert_expiry = time.time() + max_age
        log.info("Loaded %d Google signing keys (valid %ds)", len(certs), max_age)
        return _cert_cache


def _verify_with_public_keys(token: str, project_id: str) -> CurrentUser:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise ApiError("UNAUTHENTICATED", 401, message="Token tidak berbentuk JWT yang valid.") from exc

    kid = header.get("kid")
    if not kid:
        raise ApiError("UNAUTHENTICATED", 401, message="Token tidak memiliki key id.")

    certs = _fetch_certs()
    key = certs.get(kid)
    if key is None:
        global _cert_expiry
        _cert_expiry = 0.0
        key = _fetch_certs().get(kid)
    if key is None:
        raise ApiError("UNAUTHENTICATED", 401, message="Kunci penandatangan token tidak dikenal.")

    try:
        claims = jwt.decode(
            token,
            key=key,
            algorithms=["RS256"],
            audience=project_id,
            issuer=f"https://securetoken.google.com/{project_id}",
            leeway=LEEWAY_SECONDS,
            options={"require": ["exp", "iat", "aud", "iss", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise ApiError(
            "UNAUTHENTICATED", 401, message="Sesi Anda telah berakhir. Silakan login ulang."
        ) from exc
    except jwt.InvalidAudienceError as exc:
        raise ApiError(
            "UNAUTHENTICATED",
            401,
            message="Token diterbitkan untuk project Firebase yang berbeda.",
        ) from exc
    except jwt.PyJWTError as exc:
        raise ApiError("UNAUTHENTICATED", 401, message="Token Firebase tidak valid.") from exc

    uid = claims.get("sub") or ""
    if not uid:
        raise ApiError("UNAUTHENTICATED", 401, message="Token tidak memuat identitas pengguna.")

    auth_time = claims.get("auth_time")
    if auth_time and auth_time > time.time() + LEEWAY_SECONDS:
        raise ApiError("UNAUTHENTICATED", 401, message="Token Firebase tidak valid.")

    return CurrentUser(uid=uid, email=claims.get("email"), method="google-public-keys")


def verify(token: str, settings: Settings) -> CurrentUser:
    if not token:
        raise ApiError("UNAUTHENTICATED", 401)

    if _admin_available:
        from firebase_admin import auth as fb_auth

        try:
            decoded = fb_auth.verify_id_token(token)
        except Exception as exc:
            raise ApiError(
                "UNAUTHENTICATED", 401, message="Token Firebase tidak valid atau kedaluwarsa."
            ) from exc
        return CurrentUser(uid=decoded["uid"], email=decoded.get("email"), method="admin-sdk")

    if _public_key_available:
        return _verify_with_public_keys(token, settings.firebase_project_id)

    if settings.identicare_env == "dev" and token.startswith("dev:"):
        uid = token.split(":", 1)[1].strip()
        if not uid:
            raise ApiError("UNAUTHENTICATED", 401)
        log.warning("DEV MODE auth bypass used for uid=%s", uid)
        return CurrentUser(uid=uid, email=f"{uid}@dev.local", dev_mode=True, method="dev-bypass")

    raise ApiError(
        "UNAUTHENTICATED",
        401,
        message="Verifikasi Firebase tidak tersedia di server.",
    )


def reset_for_tests() -> None:
    global _initialised, _admin_available, _public_key_available, _cert_expiry
    _initialised = False
    _admin_available = False
    _public_key_available = False
    _cert_expiry = 0.0
    _cert_cache.clear()
