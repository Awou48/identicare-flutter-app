from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from pymongo import AsyncMongoClient, MongoClient
from pymongo.errors import ServerSelectionTimeoutError

from app import db as database
from app.config import get_settings
from app.routers import staff as staff_router
from app.security import crypto, staff_auth
from app.utils.errors import ApiError

NIP = "test-lockout-199001012020011001"
PASSWORD = "kata-sandi-benar"


@pytest.fixture
def account():
    settings = get_settings()
    client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=1500)
    try:
        client.admin.command("ping")
    except ServerSelectionTimeoutError:
        pytest.skip("MongoDB not reachable")
    db = client[settings.mongo_db]
    now = datetime.now(UTC)
    sid = db.staff.insert_one(
        {
            "nama": "Uji Lockout",
            "nip": NIP,
            "role": "petugas",
            "faskes_id": None,
            "password_hash": staff_auth.hash_password(PASSWORD),
            "active": True,
            "created_at": now,
            "last_login": None,
        }
    ).inserted_id
    database._kek = crypto.load_kek(settings.kek_file)
    yield settings
    database._kek = None
    db.staff.delete_one({"_id": sid})
    db.audit_log.delete_many({"who": {"$regex": "^staff-login:test-lockout"}})
    client.close()


def _login(settings, nip, password):
    async def go():
        client = AsyncMongoClient(settings.mongo_uri)
        try:
            return await staff_router.login({"nip": nip, "password": password}, client[settings.mongo_db])
        finally:
            await client.close()

    return asyncio.new_event_loop().run_until_complete(go())


def test_five_wrong_passwords_lock_the_nip_even_for_the_right_one(account):
    for _ in range(staff_router.LOGIN_MAX_FAILURES):
        with pytest.raises(ApiError) as exc:
            _login(account, NIP, "salah")
        assert exc.value.code == "UNAUTHENTICATED"
    with pytest.raises(ApiError) as exc:
        _login(account, NIP, PASSWORD)
    assert exc.value.code == "TOO_MANY_ATTEMPTS"
    assert exc.value.status_code == 429


def test_correct_password_before_the_limit_still_works(account):
    for _ in range(staff_router.LOGIN_MAX_FAILURES - 1):
        with pytest.raises(ApiError):
            _login(account, NIP, "salah")
    result = _login(account, NIP, PASSWORD)
    assert result["staff"]["role"] == "petugas"


def test_unknown_nip_is_counted_and_locked_the_same_way(account):
    ghost = "test-lockout-does-not-exist"
    for _ in range(staff_router.LOGIN_MAX_FAILURES):
        with pytest.raises(ApiError) as exc:
            _login(account, ghost, "x")
        assert exc.value.code == "UNAUTHENTICATED"
    with pytest.raises(ApiError) as exc:
        _login(account, ghost, "x")
    assert exc.value.code == "TOO_MANY_ATTEMPTS"
