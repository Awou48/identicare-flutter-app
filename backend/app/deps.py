from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header, Request
from pymongo.asynchronous.database import AsyncDatabase

from app import db as database
from app.config import Settings, get_settings
from app.security import crypto, firebase_auth, staff_auth
from app.security.firebase_auth import CurrentUser
from app.security.staff_auth import ROLE_SUPERVISOR, StaffPrincipal
from app.utils.errors import ApiError


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", uuid.uuid4().hex[:12])


def get_settings_dep() -> Settings:
    return get_settings()


def get_database() -> AsyncDatabase:
    return database.get_db()


async def current_user(
    authorization: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings_dep),
) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError("UNAUTHENTICATED", 401)
    return firebase_auth.verify(authorization[7:].strip(), settings)


async def session_token(
    x_session_token: Annotated[str | None, Header()] = None,
) -> str:
    if not x_session_token:
        raise ApiError("INVALID_SESSION_TOKEN", 403, message="Header X-Session-Token wajib diisi.")
    return x_session_token


async def operator_key(
    x_api_key: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings_dep),
) -> str:
    """Operator/admin endpoints. Enrollment must never be callable by a peserta with only their own Firebase
    token - that would let anyone enrol a face against any BPJS number.
    """
    if not x_api_key or not crypto.constant_time_equals(x_api_key, settings.operator_api_key):
        raise ApiError("INVALID_API_KEY", 403, message="API key operator tidak valid.")
    return x_api_key


async def facility_key(
    x_api_key: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings_dep),
) -> str:
    """Identifies the health facility starting a session."""
    keys = settings.facility_key_map
    if not keys and settings.identicare_env == "dev":
        return "dev"
    if not x_api_key:
        raise ApiError("INVALID_API_KEY", 403)
    for known, kode in keys.items():
        if crypto.constant_time_equals(x_api_key, known):
            return kode
    raise ApiError("INVALID_API_KEY", 403)


async def current_staff(
    x_staff_token: Annotated[str | None, Header()] = None,
) -> StaffPrincipal:
    """Authenticated staff member."""
    if not x_staff_token:
        raise ApiError("UNAUTHENTICATED", 401, message="Header X-Staff-Token wajib diisi untuk aksi petugas.")
    return staff_auth.verify_token(database.get_kek(), x_staff_token)


async def current_supervisor(
    staff: Annotated[StaffPrincipal, Depends(current_staff)],
) -> StaffPrincipal:
    staff.require(ROLE_SUPERVISOR)
    return staff


CurrentUserDep = Annotated[CurrentUser, Depends(current_user)]
StaffDep = Annotated[StaffPrincipal, Depends(current_staff)]
SupervisorDep = Annotated[StaffPrincipal, Depends(current_supervisor)]
DbDep = Annotated[AsyncDatabase, Depends(get_database)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
SessionTokenDep = Annotated[str, Depends(session_token)]
RequestIdDep = Annotated[str, Depends(get_request_id)]
OperatorDep = Annotated[str, Depends(operator_key)]
FacilityDep = Annotated[str, Depends(facility_key)]
