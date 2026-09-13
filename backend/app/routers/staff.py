"""Staff accounts and login."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bson import ObjectId
from fastapi import APIRouter

from app import db as database
from app.deps import DbDep, OperatorDep, StaffDep
from app.security import staff_auth
from app.security.staff_auth import ROLES
from app.services import audit
from app.utils.errors import ApiError

router = APIRouter(prefix="/staff", tags=["staff"])

# The override screen lives on the PARTICIPANT's phone, so the staff login
# form is in the hands of the person with the most to gain from guessing a
# nurse's password. Five wrong guesses per NIP lock that NIP for fifteen
# minutes - for everyone, including the real owner. That is the point: a
# locked-out nurse notices and reports it; a silently brute-forced one does not.
LOGIN_MAX_FAILURES = 5
LOGIN_LOCKOUT = timedelta(minutes=15)


@router.post("/login")
async def login(payload: dict, db: DbDep) -> dict:
    """Exchange credentials for a short-lived staff token (one shift).

    Failure is deliberately indistinguishable between "no such account" and
    "wrong password", so the endpoint cannot be used to enumerate staff.
    """
    nip = (payload.get("nip") or "").strip()
    password = payload.get("password") or ""
    if not nip or not password:
        raise ApiError("VALIDATION_ERROR", 422, details={"required": ["nip", "password"]})

    now = datetime.now(UTC)
    recent_failures = await db.audit_log.count_documents(
        {"who": f"staff-login:{nip}", "what": "staff_login_failed", "at": {"$gte": now - LOGIN_LOCKOUT}}
    )
    if recent_failures >= LOGIN_MAX_FAILURES:
        raise ApiError(
            "TOO_MANY_ATTEMPTS",
            429,
            message="Terlalu banyak percobaan login. Akun dikunci 15 menit.",
        )

    staff = await db.staff.find_one({"nip": nip, "active": True})
    unauthorized = ApiError("UNAUTHENTICATED", 401, message="NIP atau kata sandi salah.")
    if not staff or not staff_auth.verify_password(password, staff["password_hash"]):
        # Keyed by NIP, not by account: an unknown NIP is counted too, so the
        # lockout cannot be used to confirm which NIPs exist.
        await audit.record(db, who=f"staff-login:{nip}", what="staff_login_failed", purpose="login_petugas")
        raise unauthorized

    await db.staff.update_one({"_id": staff["_id"]}, {"$set": {"last_login": datetime.now(UTC)}})

    token = staff_auth.issue_token(
        database.get_kek(),
        staff_id=str(staff["_id"]),
        nama=staff["nama"],
        role=staff["role"],
        faskes_id=str(staff["faskes_id"]) if staff.get("faskes_id") else None,
    )
    return {
        "status": "ok",
        "token": token,
        "expires_in_seconds": int(staff_auth.TOKEN_TTL.total_seconds()),
        "staff": {
            "staff_id": str(staff["_id"]),
            "nama": staff["nama"],
            "role": staff["role"],
            "nip": staff.get("nip"),
        },
    }


@router.get("/me")
async def me(staff: StaffDep) -> dict:
    return {
        "status": "ok",
        "staff_id": staff.staff_id,
        "nama": staff.nama,
        "role": staff.role,
        "faskes_id": staff.faskes_id,
    }


@router.post("")
async def create_staff(payload: dict, db: DbDep, _: OperatorDep) -> dict:
    """Provision a staff account. Operator-key gated (bootstrap/admin tooling)."""
    nama = (payload.get("nama") or "").strip()
    nip = (payload.get("nip") or "").strip()
    role = payload.get("role")
    password = payload.get("password") or ""

    if not nama or not nip:
        raise ApiError("VALIDATION_ERROR", 422, details={"required": ["nama", "nip"]})
    if role not in ROLES:
        raise ApiError("VALIDATION_ERROR", 422, details={"role": role, "allowed": list(ROLES)})
    if len(password) < 8:
        raise ApiError("VALIDATION_ERROR", 422, message="Kata sandi minimal 8 karakter.")

    faskes_id = None
    if payload.get("kode_faskes"):
        faskes = await db.facilities.find_one({"kode_faskes": payload["kode_faskes"]})
        if not faskes:
            raise ApiError("FASKES_NOT_FOUND", 404)
        faskes_id = faskes["_id"]

    existing = await db.staff.find_one({"nip": nip})
    doc = {
        "nama": nama,
        "nip": nip,
        "role": role,
        "faskes_id": faskes_id,
        "password_hash": staff_auth.hash_password(password),
        "active": True,
        "last_login": None,
    }
    if existing:
        await db.staff.update_one({"_id": existing["_id"]}, {"$set": doc})
        staff_id = existing["_id"]
        created = False
    else:
        doc["created_at"] = datetime.now(UTC)
        staff_id = (await db.staff.insert_one(doc)).inserted_id
        created = True

    return {"status": "ok", "staff_id": str(staff_id), "created": created}


@router.get("")
async def list_staff(db: DbDep, _: OperatorDep) -> dict:
    docs = await db.staff.find({}, {"password_hash": 0}).limit(200).to_list(200)
    return {
        "status": "ok",
        "items": [
            {
                "staff_id": str(d["_id"]),
                "nama": d["nama"],
                "nip": d.get("nip"),
                "role": d["role"],
                "faskes_id": str(d["faskes_id"]) if d.get("faskes_id") else None,
                "active": d.get("active", True),
                "last_login": d.get("last_login"),
            }
            for d in docs
        ],
    }


@router.post("/{staff_id}/deactivate")
async def deactivate(staff_id: str, db: DbDep, _: OperatorDep) -> dict:
    try:
        oid = ObjectId(staff_id)
    except Exception as exc:
        raise ApiError("VALIDATION_ERROR", 422, details={"staff_id": staff_id}) from exc
    result = await db.staff.update_one({"_id": oid}, {"$set": {"active": False}})
    if result.matched_count == 0:
        raise ApiError("VALIDATION_ERROR", 404, details={"staff_id": staff_id})
    return {"status": "ok", "staff_id": staff_id, "active": False}
