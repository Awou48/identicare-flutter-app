"""Verify the Firebase ID tokens the Flutter app already produces.

The hybrid-database decision means Firebase Auth stays the identity provider and
MongoDB holds everything else. This module is the seam: it turns an ID token into
a firebase_uid, which `peserta.firebase_uid` links to a BPJS participant.

Dev fallback: when no service-account JSON is configured AND the environment is
"dev", a token of the form "dev:<uid>" is accepted so the API can be driven from
Swagger without Firebase credentials. It is refused outright in any other
environment, and every use is logged loudly - an auth bypass that can silently
follow you to production is far worse than the inconvenience it saves.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from app.utils.errors import ApiError

log = logging.getLogger(__name__)

_initialised = False
_available = False


@dataclass
class CurrentUser:
    uid: str
    email: str | None = None
    dev_mode: bool = False


def init(settings: Settings) -> bool:
    """Initialise firebase-admin if a credentials file is present."""
    global _initialised, _available
    if _initialised:
        return _available
    _initialised = True

    cred_path = Path(settings.firebase_credentials)
    if not cred_path.is_absolute():
        from app.config import BACKEND_ROOT

        cred_path = BACKEND_ROOT / cred_path

    if not cred_path.exists():
        if settings.identicare_env == "dev":
            log.warning(
                "Firebase credentials not found at %s. DEV MODE: accepting "
                "'Authorization: Bearer dev:<uid>' tokens. Never deploy like this.",
                cred_path,
            )
        else:
            log.error("Firebase credentials missing at %s - all auth will fail.", cred_path)
        _available = False
        return False

    try:
        import firebase_admin
        from firebase_admin import credentials

        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(str(cred_path)))
        _available = True
        log.info("Firebase Admin initialised from %s", cred_path)
    except Exception:
        log.exception("Failed to initialise Firebase Admin")
        _available = False
    return _available


def is_available() -> bool:
    return _available


def verify(token: str, settings: Settings) -> CurrentUser:
    if not token:
        raise ApiError("UNAUTHENTICATED", 401)

    if _available:
        from firebase_admin import auth as fb_auth

        try:
            decoded = fb_auth.verify_id_token(token)
        except Exception as exc:
            raise ApiError(
                "UNAUTHENTICATED", 401, message="Token Firebase tidak valid atau kedaluwarsa."
            ) from exc
        return CurrentUser(uid=decoded["uid"], email=decoded.get("email"))

    if settings.identicare_env == "dev" and token.startswith("dev:"):
        uid = token.split(":", 1)[1].strip()
        if not uid:
            raise ApiError("UNAUTHENTICATED", 401)
        log.warning("DEV MODE auth bypass used for uid=%s", uid)
        return CurrentUser(uid=uid, email=f"{uid}@dev.local", dev_mode=True)

    raise ApiError(
        "UNAUTHENTICATED",
        401,
        message="Verifikasi Firebase tidak tersedia di server.",
    )
