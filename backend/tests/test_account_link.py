"""POST /peserta/link - the bridge between Firebase Auth and BPJS records.

These run against a live MongoDB and skip without one. They exercise the three
guarantees the endpoint makes, in the order an attacker would probe them:
wrong identity is refused with a uniform message, an already-linked record
cannot be taken over, and guessing is rate-limited.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from pymongo import AsyncMongoClient, MongoClient
from pymongo.errors import ServerSelectionTimeoutError

from app.config import get_settings
from app.routers import peserta as peserta_router
from app.security import crypto
from app.security.firebase_auth import CurrentUser
from app.utils.errors import ApiError

NIK = "9999000011112222"
BPJS = "9990000000001"
DOB = "1990-05-17"


@pytest.fixture(scope="module")
def settings():
    return get_settings()


@pytest.fixture(scope="module")
def sync_db(settings):
    client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=1500)
    try:
        client.admin.command("ping")
    except ServerSelectionTimeoutError:
        pytest.skip("MongoDB not reachable")
    yield client[settings.mongo_db]
    client.close()


@pytest.fixture
def peserta(sync_db, settings):
    """A fresh, unlinked participant. Removed afterwards along with its audit rows."""
    now = datetime.now(UTC)
    doc = {
        "no_bpjs": BPJS,
        "nik_hash": crypto.hash_nik(NIK, settings.nik_pepper),
        "nik_last4": NIK[-4:],
        "nama_lengkap": "Uji Penautan",
        "tanggal_lahir": datetime(1990, 5, 17, tzinfo=UTC),
        "status_kepesertaan": "AKTIF",
        "firebase_uid": None,
        "biometric_enrolled": False,
        "created_at": now,
        "updated_at": now,
        "schema_version": 1,
        "_test": True,
    }
    sync_db.peserta.delete_many({"no_bpjs": BPJS})
    pid = sync_db.peserta.insert_one(doc).inserted_id
    yield pid
    sync_db.peserta.delete_many({"no_bpjs": BPJS})
    sync_db.audit_log.delete_many({"who": {"$regex": "^test-uid-"}})
    sync_db.fraud_signals.delete_many({"peserta_id": pid})


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


async def _call(settings, uid: str, **fields):
    client = AsyncMongoClient(settings.mongo_uri)
    db = client[settings.mongo_db]
    payload = peserta_router.LinkRequest(
        no_bpjs=fields.get("no_bpjs", BPJS),
        nik=fields.get("nik", NIK),
        tanggal_lahir=fields.get("tanggal_lahir", DOB),
    )
    try:
        return await peserta_router.link_account(payload, db, settings, CurrentUser(uid=uid))
    finally:
        await client.close()


def test_correct_triple_links_the_account(sync_db, settings, peserta):
    result = _run(_call(settings, "test-uid-alice"))
    assert result["linked"] is True and result["already"] is False
    assert sync_db.peserta.find_one({"_id": peserta})["firebase_uid"] == "test-uid-alice"
    assert sync_db.peserta.find_one({"_id": peserta})["linked_via"] == "self"


def test_linking_is_idempotent_for_the_same_account(settings, peserta):
    _run(_call(settings, "test-uid-alice"))
    again = _run(_call(settings, "test-uid-alice"))
    assert again["already"] is True


@pytest.mark.parametrize(
    "bad",
    [
        {"nik": "0000000000000000"},
        {"tanggal_lahir": "1991-05-17"},
        {"no_bpjs": "9990000000002"},
    ],
    ids=["wrong-nik", "wrong-dob", "unknown-bpjs"],
)
def test_wrong_identity_is_refused_with_a_uniform_message(settings, peserta, bad):
    """Every mismatch gives the same code and message. Saying WHICH field was
    wrong would turn this into an oracle for pairing NIKs with BPJS numbers."""
    with pytest.raises(ApiError) as exc:
        _run(_call(settings, "test-uid-mallory", **bad))
    assert exc.value.code == "IDENTITY_MISMATCH"
    assert exc.value.status_code == 403
    # Identical copy for every branch - including "no such BPJS number", which
    # is the case an enumerator most wants to distinguish.
    assert exc.value.message.startswith("Data tidak cocok dengan catatan BPJS.")
    assert exc.value.details["attempts_left"] == peserta_router.LINK_MAX_FAILURES - 1


def test_cannot_take_over_an_already_linked_record(sync_db, settings, peserta):
    """The takeover attempt: correct triple, but the record belongs to someone
    else. Refused, AND recorded as a fraud signal rather than silently dropped."""
    _run(_call(settings, "test-uid-alice"))
    with pytest.raises(ApiError) as exc:
        _run(_call(settings, "test-uid-mallory"))
    assert exc.value.code == "BPJS_ALREADY_LINKED"
    assert exc.value.status_code == 409
    signal = sync_db.fraud_signals.find_one({"peserta_id": peserta, "rule_id": "ACCOUNT_LINK_CONFLICT"})
    assert signal is not None and signal["severity"] == "high"
    assert signal["detail"]["attempted_by"] == "test-uid-mallory"


def test_one_account_cannot_hold_two_participants(sync_db, settings, peserta):
    other = sync_db.peserta.insert_one(
        {
            "no_bpjs": "9990000000003",
            "nik_hash": crypto.hash_nik("9999000011113333", settings.nik_pepper),
            "nik_last4": "3333",
            "nama_lengkap": "Kedua",
            "tanggal_lahir": datetime(1990, 5, 17, tzinfo=UTC),
            "status_kepesertaan": "AKTIF",
            "firebase_uid": None,
            "biometric_enrolled": False,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "schema_version": 1,
        }
    ).inserted_id
    try:
        _run(_call(settings, "test-uid-alice"))
        with pytest.raises(ApiError) as exc:
            _run(_call(settings, "test-uid-alice", no_bpjs="9990000000003", nik="9999000011113333"))
        assert exc.value.code == "ACCOUNT_ALREADY_LINKED"
    finally:
        sync_db.peserta.delete_one({"_id": other})


def test_guessing_is_rate_limited(settings, peserta):
    """Five wrong guesses in an hour, then the door closes - even for a correct
    sixth attempt. Without this the NIK space could be walked."""
    for _ in range(peserta_router.LINK_MAX_FAILURES):
        with pytest.raises(ApiError):
            _run(_call(settings, "test-uid-bruteforce", nik="1111111111111111"))
    with pytest.raises(ApiError) as exc:
        _run(_call(settings, "test-uid-bruteforce"))  # correct, but too late
    assert exc.value.code == "TOO_MANY_ATTEMPTS"
    assert exc.value.status_code == 429


def test_me_returns_full_number_only_to_the_owner(sync_db, settings, peserta):
    _run(_call(settings, "test-uid-alice"))

    async def me(uid):
        client = AsyncMongoClient(settings.mongo_uri)
        try:
            return await peserta_router.my_status(client[settings.mongo_db], CurrentUser(uid=uid))
        finally:
            await client.close()

    mine = _run(me("test-uid-alice"))
    assert mine["no_bpjs"] == BPJS
    assert "*" in mine["no_bpjs_masked"]
    with pytest.raises(ApiError) as exc:
        _run(me("test-uid-stranger"))
    assert exc.value.code == "PESERTA_NOT_FOUND"
