"""Single source of truth for the MongoDB layout.

Collections, $jsonSchema validators and indexes live here so that
scripts/bootstrap.py, the tests and the docs can never drift apart.

Conventions:
  * All timestamps are BSON date in UTC. Flutter renders WIB.
  * NIK and no_bpjs are STRINGS. A 16-digit NIK stored as a double loses
    precision and would silently corrupt identities.
  * Validators run at validationLevel "moderate": they reject bad inserts but do
    not block updates to documents that predate a schema change.
"""

from __future__ import annotations

from typing import Any

from pymongo import ASCENDING, DESCENDING, GEOSPHERE, TEXT
from pymongo.operations import IndexModel

# --------------------------------------------------------------------------- #
# Enumerations, shared with the Pydantic schemas in app/schemas/
# --------------------------------------------------------------------------- #
STATUS_KEPESERTAAN = ["AKTIF", "NONAKTIF", "MENUNGGAK"]
JENIS_PESERTA = ["PBI", "PPU", "PBPU", "BP"]
JENIS_KELAMIN = ["L", "P"]

SESSION_STATUS = [
    "created",
    "face_passed",
    "fingerprint_passed",
    "reviewed",
    "committed",
    "rejected",
    "expired",
    "cancelled",
]
STEP_NAMES = ["face", "fingerprint", "review", "commit"]
STEP_STATUS = ["pending", "passed", "failed"]
DECISIONS = ["APPROVED", "REVIEW", "REJECTED"]
RISK_BANDS = ["LOW", "MEDIUM", "HIGH"]

MODALITIES = ["face", "fingerprint_key"]
TEMPLATE_STATUS = ["active", "revoked", "superseded"]
SECURITY_LEVELS = ["TEE", "STRONGBOX", "SOFTWARE"]
TRUST_LEVELS = ["hardware", "software", "untrusted"]
SEVERITIES = ["info", "low", "medium", "high", "critical"]
SIGNAL_STATUS = ["open", "reviewing", "confirmed", "dismissed"]

# The encrypted envelope, reused by several collections.
_ENC_ENVELOPE = {
    "bsonType": "object",
    "required": ["alg", "dek_wrapped", "dek_nonce", "nonce", "ciphertext", "aad"],
    "properties": {
        "alg": {"enum": ["AES-256-GCM"]},
        "kek_id": {"bsonType": "string"},
        "dek_wrapped": {"bsonType": "binData"},
        "dek_nonce": {"bsonType": "binData"},
        "nonce": {"bsonType": "binData"},
        "ciphertext": {"bsonType": "binData"},
        "aad": {"bsonType": "string"},
    },
}

_GEO_POINT = {
    "bsonType": "object",
    "required": ["type", "coordinates"],
    "properties": {
        "type": {"enum": ["Point"]},
        # GeoJSON order is [longitude, latitude] - the reverse of how humans say it.
        "coordinates": {"bsonType": "array", "minItems": 2, "maxItems": 2},
    },
}


# --------------------------------------------------------------------------- #
# Validators
# --------------------------------------------------------------------------- #
VALIDATORS: dict[str, dict[str, Any]] = {
    "peserta": {
        "bsonType": "object",
        "required": [
            "no_bpjs",
            "nik_hash",
            "nama_lengkap",
            "status_kepesertaan",
            "created_at",
        ],
        "properties": {
            "no_bpjs": {"bsonType": "string", "pattern": "^[0-9]{13}$"},
            "nik_hash": {"bsonType": "string", "pattern": "^[0-9a-f]{64}$"},
            "nik_enc": _ENC_ENVELOPE,
            "nik_last4": {"bsonType": "string", "pattern": "^[0-9]{4}$"},
            "nama_lengkap": {"bsonType": "string", "minLength": 1},
            "tanggal_lahir": {"bsonType": "date"},
            "jenis_kelamin": {"enum": JENIS_KELAMIN},
            "alamat": {"bsonType": "object"},
            "no_hp_enc": _ENC_ENVELOPE,
            "kelas_rawat": {"bsonType": "int", "minimum": 1, "maximum": 3},
            "jenis_peserta": {"enum": JENIS_PESERTA},
            "faskes_tingkat1": {"bsonType": "object"},
            "status_kepesertaan": {"enum": STATUS_KEPESERTAAN},
            "tunggakan_bulan": {"bsonType": "int", "minimum": 0},
            "eligibility_score": {"bsonType": "int", "minimum": 0, "maximum": 100},
            "firebase_uid": {"bsonType": ["string", "null"]},
            "biometric_enrolled": {"bsonType": "bool"},
            "biometric_enrolled_at": {"bsonType": ["date", "null"]},
            "created_at": {"bsonType": "date"},
            "updated_at": {"bsonType": "date"},
            "schema_version": {"bsonType": "int"},
        },
    },
    "biometric_templates": {
        "bsonType": "object",
        "required": ["peserta_id", "modality", "status", "created_at"],
        "properties": {
            "peserta_id": {"bsonType": "objectId"},
            "modality": {"enum": MODALITIES},
            "version": {"bsonType": "int"},
            "model": {"bsonType": "object"},
            "enc": _ENC_ENVELOPE,
            # Rotated into the secret basis; cosine-equivalent, never decrypted.
            "search_vector": {"bsonType": "array"},
            "rotation_id": {"bsonType": "string"},
            "quality": {"bsonType": "object"},
            "enroll_meta": {"bsonType": "object"},
            # fingerprint_key documents carry a PUBLIC key, so no encryption.
            "device_id": {"bsonType": "objectId"},
            "public_key_der": {"bsonType": "binData"},
            "curve": {"bsonType": "string"},
            "attestation": {"bsonType": "object"},
            "status": {"enum": TEMPLATE_STATUS},
            "created_at": {"bsonType": "date"},
            "revoked_at": {"bsonType": ["date", "null"]},
            "schema_version": {"bsonType": "int"},
        },
    },
    "devices": {
        "bsonType": "object",
        "required": ["device_uid", "platform", "first_seen"],
        "properties": {
            "device_uid": {"bsonType": "string", "minLength": 16},
            "firebase_uid": {"bsonType": ["string", "null"]},
            # More than one peserta on one device is a shared-device fraud signal.
            "peserta_ids": {"bsonType": "array"},
            "platform": {"bsonType": "string"},
            # Optional client-supplied fields: a phone that does not report its
            # model writes null, so the validator must accept null or every such
            # enrolment fails with an opaque code 121.
            "os_version": {"bsonType": ["string", "null"]},
            "model": {"bsonType": ["string", "null"]},
            "app_version": {"bsonType": ["string", "null"]},
            "attestation": {"bsonType": "object"},
            "public_key_der": {"bsonType": "binData"},
            "secret_enc": _ENC_ENVELOPE,
            "key_alias": {"bsonType": ["string", "null"]},
            "trust_level": {"enum": TRUST_LEVELS},
            "first_seen": {"bsonType": "date"},
            "last_seen": {"bsonType": "date"},
            "blocked": {"bsonType": "bool"},
        },
    },
    "facilities": {
        "bsonType": "object",
        "required": ["kode_faskes", "nama", "geo"],
        "properties": {
            "kode_faskes": {"bsonType": "string", "minLength": 3},
            "nama": {"bsonType": "string"},
            "jenis": {"bsonType": "string"},
            "tingkat": {"bsonType": "int"},
            "alamat": {"bsonType": "string"},
            "kota": {"bsonType": "string"},
            "provinsi": {"bsonType": "string"},
            "geo": _GEO_POINT,
            "api_key_hash": {"bsonType": "string"},
            "active": {"bsonType": "bool"},
        },
    },
    "verification_sessions": {
        "bsonType": "object",
        "required": [
            "session_token",
            "status",
            "peserta_id",
            "created_at",
            "expires_at",
        ],
        "properties": {
            "session_token": {"bsonType": "string", "minLength": 32},
            "status": {"enum": SESSION_STATUS},
            "peserta_id": {"bsonType": "objectId"},
            "no_bpjs": {"bsonType": "string"},
            "claim": {"bsonType": "object"},
            "context": {"bsonType": "object"},
            "required_steps": {"bsonType": "array"},
            "nonce": {"bsonType": ["string", "null"]},
            "nonce_expires_at": {"bsonType": ["date", "null"]},
            "steps": {"bsonType": "object"},
            "risk": {"bsonType": "object"},
            "result": {"bsonType": ["object", "null"]},
            "idempotency_key": {"bsonType": ["string", "null"]},
            "created_at": {"bsonType": "date"},
            "updated_at": {"bsonType": "date"},
            "expires_at": {"bsonType": "date"},
            "schema_version": {"bsonType": "int"},
        },
    },
    "verification_events": {
        "bsonType": "object",
        "required": ["session_id", "seq", "step", "outcome", "at"],
        "properties": {
            "session_id": {"bsonType": "objectId"},
            "peserta_id": {"bsonType": ["objectId", "null"]},
            "seq": {"bsonType": "int", "minimum": 0},
            "step": {"enum": STEP_NAMES + ["session"]},
            "outcome": {
                "enum": ["passed", "failed", "started", "cancelled", "expired"]
            },
            "method": {"bsonType": "string"},
            "scores": {"bsonType": "object"},
            "error_code": {"bsonType": ["string", "null"]},
            "device_uid": {"bsonType": ["string", "null"]},
            "faskes_id": {"bsonType": ["objectId", "null"]},
            "geo": _GEO_POINT,
            "latency_ms": {"bsonType": ["int", "double", "null"]},
            "request_id": {"bsonType": ["string", "null"]},
            "at": {"bsonType": "date"},
        },
    },
    "fraud_signals": {
        "bsonType": "object",
        "required": [
            "peserta_id",
            "rule_id",
            "severity",
            "weight",
            "status",
            "detected_at",
        ],
        "properties": {
            "peserta_id": {"bsonType": "objectId"},
            "session_id": {"bsonType": ["objectId", "null"]},
            "rule_id": {"bsonType": "string"},
            "severity": {"enum": SEVERITIES},
            "weight": {"bsonType": "int", "minimum": 0, "maximum": 100},
            "title": {"bsonType": "string"},
            "detail": {"bsonType": "object"},
            "status": {"enum": SIGNAL_STATUS},
            "detected_at": {"bsonType": "date"},
            "resolved_at": {"bsonType": ["date", "null"]},
            "resolved_by": {"bsonType": ["string", "null"]},
        },
    },
    "nonces": {
        "bsonType": "object",
        "required": ["_id", "purpose", "used", "issued_at", "expires_at"],
        "properties": {
            "_id": {"bsonType": "string"},
            "session_id": {"bsonType": ["objectId", "null"]},
            "purpose": {"bsonType": "string"},
            "used": {"bsonType": "bool"},
            "issued_at": {"bsonType": "date"},
            "expires_at": {"bsonType": "date"},
        },
    },
    "audit_log": {
        "bsonType": "object",
        "required": ["who", "what", "at"],
        "properties": {
            "who": {"bsonType": "string"},
            "what": {"bsonType": "string"},
            "peserta_id": {"bsonType": ["objectId", "null"]},
            "session_id": {"bsonType": ["objectId", "null"]},
            "purpose": {"bsonType": "string"},
            "at": {"bsonType": "date"},
        },
    },
}


# --------------------------------------------------------------------------- #
# Indexes
# --------------------------------------------------------------------------- #
INDEXES: dict[str, list[IndexModel]] = {
    "peserta": [
        IndexModel([("no_bpjs", ASCENDING)], name="uniq_no_bpjs", unique=True),
        IndexModel([("nik_hash", ASCENDING)], name="uniq_nik_hash", unique=True),
        IndexModel(
            [("firebase_uid", ASCENDING)],
            name="uniq_firebase_uid",
            unique=True,
            partialFilterExpression={"firebase_uid": {"$type": "string"}},
        ),
        IndexModel(
            [
                ("faskes_tingkat1.faskes_id", ASCENDING),
                ("status_kepesertaan", ASCENDING),
            ],
            name="faskes_status",
        ),
        IndexModel([("nama_lengkap", TEXT)], name="text_nama"),
    ],
    "biometric_templates": [
        IndexModel(
            [
                ("peserta_id", ASCENDING),
                ("modality", ASCENDING),
                ("status", ASCENDING),
            ],
            name="peserta_modality_status",
        ),
        # Drives the 1:N collision sweep over search_vector.
        IndexModel(
            [("status", ASCENDING), ("modality", ASCENDING)], name="status_modality"
        ),
        IndexModel([("created_at", DESCENDING)], name="created_desc"),
    ],
    "devices": [
        IndexModel([("device_uid", ASCENDING)], name="uniq_device_uid", unique=True),
        IndexModel([("firebase_uid", ASCENDING)], name="firebase_uid"),
        IndexModel([("peserta_ids", ASCENDING)], name="peserta_ids"),
        IndexModel([("blocked", ASCENDING)], name="blocked"),
    ],
    "facilities": [
        IndexModel([("kode_faskes", ASCENDING)], name="uniq_kode_faskes", unique=True),
        # Makes the impossible-travel check a one-line $geoNear.
        IndexModel([("geo", GEOSPHERE)], name="geo_2dsphere"),
    ],
    "verification_sessions": [
        IndexModel(
            [("session_token", ASCENDING)], name="uniq_session_token", unique=True
        ),
        IndexModel(
            [("peserta_id", ASCENDING), ("created_at", DESCENDING)],
            name="peserta_recent",
        ),
        IndexModel(
            [("context.faskes_id", ASCENDING), ("created_at", DESCENDING)],
            name="faskes_recent",
        ),
        IndexModel(
            [("result.decision", ASCENDING), ("created_at", DESCENDING)],
            name="decision_recent",
        ),
        IndexModel(
            [("context.device_uid", ASCENDING), ("created_at", DESCENDING)],
            name="device_recent",
        ),
        IndexModel(
            [
                ("peserta_id", ASCENDING),
                ("status", ASCENDING),
                ("created_at", DESCENDING),
            ],
            name="duplicate_claim_lookup",
        ),
        # PARTIAL TTL - this is load-bearing. Only sessions that were never started
        # self-delete. A plain TTL here would quietly eat every completed session,
        # and those are the permanent audit log. Asserted in
        # tests/test_session_state_machine.py.
        IndexModel(
            [("expires_at", ASCENDING)],
            name="ttl_abandoned_only",
            expireAfterSeconds=0,
            partialFilterExpression={"status": "created"},
        ),
    ],
    "verification_events": [
        IndexModel(
            [("session_id", ASCENDING), ("seq", ASCENDING)],
            name="uniq_session_seq",
            unique=True,
        ),
        IndexModel(
            [("peserta_id", ASCENDING), ("at", DESCENDING)], name="peserta_recent"
        ),
        IndexModel(
            [("step", ASCENDING), ("outcome", ASCENDING), ("at", DESCENDING)],
            name="step_outcome_recent",
        ),
        IndexModel([("geo", GEOSPHERE)], name="geo_2dsphere"),
    ],
    "fraud_signals": [
        IndexModel(
            [("peserta_id", ASCENDING), ("detected_at", DESCENDING)],
            name="peserta_recent",
        ),
        IndexModel(
            [
                ("status", ASCENDING),
                ("severity", ASCENDING),
                ("detected_at", DESCENDING),
            ],
            name="triage_queue",
        ),
        IndexModel(
            [("rule_id", ASCENDING), ("detected_at", DESCENDING)], name="rule_recent"
        ),
        IndexModel([("session_id", ASCENDING)], name="session"),
    ],
    "nonces": [
        # Full TTL is correct here: a nonce past its expiry has no audit value,
        # the verification_events entry already records that it was used.
        IndexModel(
            [("expires_at", ASCENDING)], name="ttl_nonce", expireAfterSeconds=0
        ),
        IndexModel([("session_id", ASCENDING)], name="session"),
    ],
    "audit_log": [
        IndexModel(
            [("peserta_id", ASCENDING), ("at", DESCENDING)], name="peserta_recent"
        ),
        IndexModel([("at", DESCENDING)], name="recent"),
    ],
}

COLLECTIONS = list(VALIDATORS.keys())
