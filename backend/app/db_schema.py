from __future__ import annotations

from typing import Any

from pymongo import ASCENDING, DESCENDING, GEOSPHERE, TEXT
from pymongo.operations import IndexModel

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
    "override_pending",
    "override_rejected",
]
STEP_NAMES = ["face", "fingerprint", "review", "commit"]
STEP_STATUS = ["pending", "passed", "failed"]
DECISIONS = ["APPROVED", "APPROVED_WITH_OVERRIDE", "REVIEW", "REJECTED"]
RISK_BANDS = ["LOW", "MEDIUM", "HIGH"]

MODALITIES = ["face", "fingerprint_key"]
TEMPLATE_STATUS = ["active", "revoked", "superseded"]
SECURITY_LEVELS = ["TEE", "STRONGBOX", "SOFTWARE"]
TRUST_LEVELS = ["hardware", "software", "untrusted"]
SEVERITIES = ["info", "low", "medium", "high", "critical"]
SIGNAL_STATUS = ["open", "reviewing", "confirmed", "dismissed"]

STAFF_ROLES = ["petugas", "supervisor", "investigator", "admin"]

ASSURANCE_LEVELS = ["SELF_ASSERTED", "DUKCAPIL_VERIFIED", "ASSISTED_DUAL_CONTROL"]

ENROLLMENT_STATUS = [
    "draft",
    "pending_dedup",
    "pending_approval",
    "approved",
    "rejected_duplicate",
    "rejected_review",
]

OVERRIDE_REASONS = [
    "CEDERA_WAJAH",
    "LUKA_BAKAR_JARI",
    "DISABILITAS",
    "KEGAGALAN_PERANGKAT",
    "PENCAHAYAAN_BURUK",
    "LAINNYA",
]

CONSENT_PURPOSES = ["biometric_enrollment", "biometric_verification", "fraud_analytics"]

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
        "coordinates": {"bsonType": "array", "minItems": 2, "maxItems": 2},
    },
}


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
            "search_vector": {"bsonType": "array"},
            "rotation_id": {"bsonType": "string"},
            "quality": {"bsonType": "object"},
            "enroll_meta": {"bsonType": "object"},
            "device_id": {"bsonType": "objectId"},
            "public_key_der": {"bsonType": "binData"},
            "curve": {"bsonType": "string"},
            "attestation": {"bsonType": "object"},
            "status": {"enum": TEMPLATE_STATUS},
            "assurance": {"enum": ASSURANCE_LEVELS},
            "enrollment_request_id": {"bsonType": ["objectId", "null"]},
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
            "peserta_ids": {"bsonType": "array"},
            "platform": {"bsonType": "string"},
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
            "override": {"bsonType": ["object", "null"]},
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
            "outcome": {"enum": ["passed", "failed", "started", "cancelled", "expired"]},
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
    "staff": {
        "bsonType": "object",
        "required": ["nama", "role", "password_hash", "active", "created_at"],
        "properties": {
            "nama": {"bsonType": "string", "minLength": 1},
            "nip": {"bsonType": ["string", "null"]},
            "role": {"enum": STAFF_ROLES},
            "faskes_id": {"bsonType": ["objectId", "null"]},
            "password_hash": {"bsonType": "string", "minLength": 20},
            "active": {"bsonType": "bool"},
            "created_at": {"bsonType": "date"},
            "last_login": {"bsonType": ["date", "null"]},
        },
    },
    "enrollment_requests": {
        "bsonType": "object",
        "required": ["no_bpjs", "status", "assurance", "created_at"],
        "properties": {
            "no_bpjs": {"bsonType": "string", "pattern": "^[0-9]{13}$"},
            "peserta_id": {"bsonType": ["objectId", "null"]},
            "status": {"enum": ENROLLMENT_STATUS},
            "assurance": {"enum": ASSURANCE_LEVELS},
            "captured_by": {"bsonType": ["objectId", "null"]},
            "approved_by": {"bsonType": ["objectId", "null"]},
            "faskes_id": {"bsonType": ["objectId", "null"]},
            "dedup": {"bsonType": "object"},
            "quality": {"bsonType": "object"},
            "rejection_reason": {"bsonType": ["string", "null"]},
            "template_id": {"bsonType": ["objectId", "null"]},
            "evidence": {"bsonType": "object"},
            "dukcapil": {"bsonType": "object"},
            "created_at": {"bsonType": "date"},
            "updated_at": {"bsonType": "date"},
            "decided_at": {"bsonType": ["date", "null"]},
            "schema_version": {"bsonType": "int"},
        },
    },
    "consent": {
        "bsonType": "object",
        "required": ["peserta_id", "purpose", "version", "granted_at"],
        "properties": {
            "peserta_id": {"bsonType": "objectId"},
            "purpose": {"enum": CONSENT_PURPOSES},
            "version": {"bsonType": "string"},
            "text_hash": {"bsonType": "string", "pattern": "^[0-9a-f]{64}$"},
            "granted_at": {"bsonType": "date"},
            "granted_via": {"bsonType": "string"},
            "revoked_at": {"bsonType": ["date", "null"]},
            "evidence": {"bsonType": "object"},
        },
    },
    "articles": {
        "bsonType": "object",
        "required": ["slug", "judul", "published"],
        "properties": {
            "slug": {"bsonType": "string", "minLength": 1},
            "judul": {"bsonType": "string", "minLength": 1},
            "ringkasan": {"bsonType": "string"},
            "konten": {"bsonType": "string"},
            "kategori": {"bsonType": "string"},
            "image_url": {"bsonType": ["string", "null"]},
            "penulis": {"bsonType": ["string", "null"]},
            "sumber": {"bsonType": ["string", "null"]},
            "featured": {"bsonType": "bool"},
            "published": {"bsonType": "bool"},
            "reading_minutes": {"bsonType": "int", "minimum": 1},
            "views": {"bsonType": "int", "minimum": 0},
            "published_at": {"bsonType": "date"},
            "updated_at": {"bsonType": "date"},
            "seeded": {"bsonType": "bool"},
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
        IndexModel([("status", ASCENDING), ("modality", ASCENDING)], name="status_modality"),
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
        IndexModel([("geo", GEOSPHERE)], name="geo_2dsphere"),
    ],
    "verification_sessions": [
        IndexModel([("session_token", ASCENDING)], name="uniq_session_token", unique=True),
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
        IndexModel(
            [("override.approved_by", ASCENDING), ("created_at", DESCENDING)],
            name="override_by_staff",
            partialFilterExpression={"override.approved_by": {"$exists": True}},
        ),
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
        IndexModel([("peserta_id", ASCENDING), ("at", DESCENDING)], name="peserta_recent"),
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
        IndexModel([("rule_id", ASCENDING), ("detected_at", DESCENDING)], name="rule_recent"),
        IndexModel([("session_id", ASCENDING)], name="session"),
    ],
    "nonces": [
        IndexModel([("expires_at", ASCENDING)], name="ttl_nonce", expireAfterSeconds=0),
        IndexModel([("session_id", ASCENDING)], name="session"),
    ],
    "staff": [
        IndexModel(
            [("nip", ASCENDING)],
            name="uniq_nip",
            unique=True,
            partialFilterExpression={"nip": {"$type": "string"}},
        ),
        IndexModel([("faskes_id", ASCENDING), ("role", ASCENDING)], name="faskes_role"),
        IndexModel([("active", ASCENDING)], name="active"),
    ],
    "enrollment_requests": [
        IndexModel([("no_bpjs", ASCENDING), ("created_at", DESCENDING)], name="bpjs_recent"),
        IndexModel([("status", ASCENDING), ("created_at", DESCENDING)], name="status_recent"),
        IndexModel([("captured_by", ASCENDING), ("created_at", DESCENDING)], name="capturer_recent"),
        IndexModel(
            [("no_bpjs", ASCENDING)],
            name="uniq_inflight_per_peserta",
            unique=True,
            partialFilterExpression={"status": {"$in": ["draft", "pending_dedup", "pending_approval"]}},
        ),
    ],
    "consent": [
        IndexModel([("peserta_id", ASCENDING), ("purpose", ASCENDING)], name="peserta_purpose"),
        IndexModel([("revoked_at", ASCENDING)], name="revoked"),
    ],
    "articles": [
        IndexModel([("slug", ASCENDING)], name="uniq_slug", unique=True),
        IndexModel(
            [("published", ASCENDING), ("featured", DESCENDING), ("published_at", DESCENDING)],
            name="published_featured_recent",
        ),
        IndexModel([("kategori", ASCENDING), ("published_at", DESCENDING)], name="kategori_recent"),
    ],
    "audit_log": [
        IndexModel([("peserta_id", ASCENDING), ("at", DESCENDING)], name="peserta_recent"),
        IndexModel([("at", DESCENDING)], name="recent"),
    ],
}

COLLECTIONS = list(VALIDATORS.keys())
