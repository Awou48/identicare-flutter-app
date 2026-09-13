from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError, WriteError

from app.config import get_settings
from app.db_schema import COLLECTIONS, INDEXES


@pytest.fixture(scope="module")
def db():
    settings = get_settings()
    client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=1500)
    try:
        client.admin.command("ping")
    except ServerSelectionTimeoutError:
        pytest.skip("MongoDB not reachable - run docker compose up -d and bootstrap.py")
    database = client[settings.mongo_db]
    if "peserta" not in database.list_collection_names():
        pytest.skip("Database not bootstrapped - run scripts/bootstrap.py")
    yield database
    client.close()


def test_all_collections_exist(db) -> None:
    present = set(db.list_collection_names())
    missing = [c for c in COLLECTIONS if c not in present]
    assert not missing, f"missing collections: {missing}"


@pytest.mark.parametrize("name", list(INDEXES.keys()))
def test_declared_indexes_exist(db, name: str) -> None:
    actual = {idx["name"] for idx in db[name].list_indexes()}
    expected = {m.document["name"] for m in INDEXES[name]}
    assert expected <= actual, f"{name} missing {expected - actual}"


def test_ttl_on_sessions_is_partial(db) -> None:
    """The trap. A non-partial TTL on verification_sessions deletes committed sessions, which are the
    permanent verification audit log the whole product is supposed to produce. Nothing would raise; the
    history would just empty out.
    """
    idx = next(
        (i for i in db.verification_sessions.list_indexes() if i["name"] == "ttl_abandoned_only"),
        None,
    )
    assert idx is not None, "ttl_abandoned_only index is missing"
    assert "expireAfterSeconds" in idx, "index is not a TTL index"
    assert idx.get("partialFilterExpression") == {"status": "created"}, (
        f"TTL is NOT partial - it would expire committed sessions. Got: {idx.get('partialFilterExpression')}"
    )


def test_nonce_ttl_is_full(db) -> None:
    """By contrast, nonces SHOULD expire unconditionally - the event log already records that one was
    consumed, so the nonce itself has no audit value.
    """
    idx = next((i for i in db.nonces.list_indexes() if i["name"] == "ttl_nonce"), None)
    assert idx is not None
    assert "expireAfterSeconds" in idx
    assert "partialFilterExpression" not in idx


def test_unique_constraints(db) -> None:
    unique_expected = {
        "peserta": {"uniq_no_bpjs", "uniq_nik_hash", "uniq_firebase_uid"},
        "devices": {"uniq_device_uid"},
        "facilities": {"uniq_kode_faskes"},
        "verification_sessions": {"uniq_session_token"},
        "verification_events": {"uniq_session_seq"},
    }
    for coll, names in unique_expected.items():
        actual = {i["name"] for i in db[coll].list_indexes() if i.get("unique")}
        assert names <= actual, f"{coll} not unique: {names - actual}"


def test_geospatial_indexes(db) -> None:
    for coll in ("facilities", "verification_events"):
        kinds = [v for i in db[coll].list_indexes() for v in i["key"].values()]
        assert "2dsphere" in kinds, f"{coll} has no 2dsphere index"


def test_validator_rejects_bad_peserta(db) -> None:
    """no_bpjs must be a 13-digit STRING. Storing it as a number would lose precision on a 16-digit NIK and
    silently corrupt identities.
    """
    with pytest.raises(WriteError):
        db.peserta.insert_one(
            {
                "no_bpjs": 1234567890123,
                "nik_hash": "a" * 64,
                "nama_lengkap": "Test",
                "status_kepesertaan": "AKTIF",
                "created_at": datetime.now(UTC),
                "_test": True,
            }
        )


def test_validator_rejects_unknown_status(db) -> None:
    with pytest.raises(WriteError):
        db.peserta.insert_one(
            {
                "no_bpjs": "9999999999999",
                "nik_hash": "b" * 64,
                "nama_lengkap": "Test",
                "status_kepesertaan": "MUNGKIN_AKTIF",
                "created_at": datetime.now(UTC),
                "_test": True,
            }
        )


def test_validator_rejects_bad_session_status(db) -> None:
    from bson import ObjectId

    with pytest.raises(WriteError):
        db.verification_sessions.insert_one(
            {
                "session_token": "x" * 32,
                "status": "halfway_done",
                "peserta_id": ObjectId(),
                "created_at": datetime.now(UTC),
                "expires_at": datetime.now(UTC) + timedelta(minutes=10),
                "_test": True,
            }
        )


def test_validator_accepts_a_valid_session(db) -> None:
    from bson import ObjectId

    doc = {
        "session_token": "t" * 32,
        "status": "created",
        "peserta_id": ObjectId(),
        "no_bpjs": "0001234567890",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "expires_at": datetime.now(UTC) + timedelta(minutes=10),
        "schema_version": 1,
        "_test": True,
    }
    result = db.verification_sessions.insert_one(doc)
    try:
        assert db.verification_sessions.find_one({"_id": result.inserted_id})
    finally:
        db.verification_sessions.delete_one({"_id": result.inserted_id})
