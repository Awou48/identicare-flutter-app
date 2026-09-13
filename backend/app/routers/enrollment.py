"""Enrollment: participants, faces, devices. Operator-authenticated.

These endpoints deliberately require an operator key rather than the peserta's
own Firebase token. If a participant could call /enrollment/face themselves, they
could enrol their own face against somebody else's BPJS number - which is exactly
the fraud this system exists to prevent.
"""

from __future__ import annotations

import base64
import logging
from datetime import UTC, datetime

import numpy as np
from bson import ObjectId
from fastapi import APIRouter, File, Form, UploadFile
from starlette.concurrency import run_in_threadpool

from app import db as database
from app.deps import CurrentUserDep, DbDep, OperatorDep, RequestIdDep, SettingsDep
from app.schemas.common import OkResponse
from app.schemas.peserta import PesertaCreate, PesertaCreated
from app.security import attestation, crypto, rotation
from app.services import audit, enrollment_service, face_engine, matcher
from app.utils import images
from app.utils.errors import ApiError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/enrollment", tags=["enrollment"])

# Two enrolment frames of the same person should agree strongly. Below this the
# operator most likely captured two different people, or one badly blurred shot.
ENROLL_CONSISTENCY_MIN = 0.60


@router.post("/peserta", response_model=PesertaCreated)
async def upsert_peserta(
    payload: PesertaCreate, db: DbDep, settings: SettingsDep, _: OperatorDep
) -> PesertaCreated:
    faskes = await db.facilities.find_one({"kode_faskes": payload.kode_faskes_tingkat1})
    if not faskes:
        raise ApiError("FASKES_NOT_FOUND", 404)

    now = datetime.now(UTC)
    nik_hash = crypto.hash_nik(payload.nik, settings.nik_pepper)

    doc = {
        "no_bpjs": payload.no_bpjs,
        "nik_hash": nik_hash,
        "nik_last4": payload.nik[-4:],
        "nama_lengkap": payload.nama_lengkap,
        "tanggal_lahir": datetime.combine(payload.tanggal_lahir, datetime.min.time()).replace(tzinfo=UTC),
        "jenis_kelamin": payload.jenis_kelamin,
        "alamat": payload.alamat.model_dump(),
        "kelas_rawat": payload.kelas_rawat,
        "jenis_peserta": payload.jenis_peserta,
        "faskes_tingkat1": {"faskes_id": faskes["_id"], "nama": faskes["nama"]},
        "status_kepesertaan": payload.status_kepesertaan,
        "tunggakan_bulan": payload.tunggakan_bulan,
        "eligibility_score": max(0, 100 - payload.tunggakan_bulan * 15),
        "firebase_uid": payload.firebase_uid,
        "updated_at": now,
        "schema_version": 1,
    }

    existing = await db.peserta.find_one({"no_bpjs": payload.no_bpjs}, {"_id": 1})
    if existing:
        peserta_id = existing["_id"]
        await db.peserta.update_one({"_id": peserta_id}, {"$set": doc})
        created = False
    else:
        doc["created_at"] = now
        doc["biometric_enrolled"] = False
        doc["biometric_enrolled_at"] = None
        result = await db.peserta.insert_one(doc)
        peserta_id = result.inserted_id
        created = True

    # NIK is encrypted under an AAD bound to this document, so the ciphertext
    # cannot be transplanted onto another participant.
    kek = database.get_kek()
    aad = crypto.build_aad(peserta_id, "nik", 1)
    await db.peserta.update_one(
        {"_id": peserta_id},
        {"$set": {"nik_enc": crypto.encrypt_blob(kek, payload.nik.encode(), aad)}},
    )
    if payload.no_hp:
        hp_aad = crypto.build_aad(peserta_id, "no_hp", 1)
        await db.peserta.update_one(
            {"_id": peserta_id},
            {"$set": {"no_hp_enc": crypto.encrypt_blob(kek, payload.no_hp.encode(), hp_aad)}},
        )

    return PesertaCreated(peserta_id=str(peserta_id), no_bpjs=payload.no_bpjs, created=created)


@router.post("/face")
async def enroll_face(
    db: DbDep,
    settings: SettingsDep,
    request_id: RequestIdDep,
    _: OperatorDep,
    no_bpjs: str = Form(...),
    frames: list[UploadFile] = File(...),
    replace: bool = Form(False),
    assurance: str = Form(enrollment_service.ASSURANCE_SELF),
) -> dict:
    """Operator-driven enrolment from a 3-frame burst."""
    peserta = await db.peserta.find_one({"no_bpjs": no_bpjs})
    if not peserta:
        raise ApiError("PESERTA_NOT_FOUND", 404)

    payloads = [await f.read() for f in frames] if frames else []
    return await _run_enrollment(
        db,
        settings,
        peserta=peserta,
        payloads=payloads,
        assurance=assurance,
        replace=replace,
        actor="operator",
        request_id=request_id,
    )


@router.post("/self")
async def enroll_self(
    db: DbDep,
    settings: SettingsDep,
    request_id: RequestIdDep,
    user: CurrentUserDep,
    frames: list[UploadFile] = File(...),
) -> dict:
    """Self-service enrolment by the participant, from their own phone.

    Why this exists: the claim flow refuses to start with BIOMETRIC_NOT_ENROLLED,
    and until now the app had no way to resolve that - the headline feature
    simply dead-ended for anyone an operator had not enrolled first.

    Three deliberate differences from the operator path.

    1. Authenticated by the participant's own Firebase token, NOT the operator
       key. Shipping the operator key inside the patient app would hand every
       user the ability to enrol any face against any BPJS number, which is the
       exact hole the dedup gate exists to close.
    2. The participant is resolved from firebase_uid, never from a body field.
       Accepting a no_bpjs here would let anyone enrol their face against
       someone else's number just by typing it.
    3. replace is not offered. Re-enrolling over an existing template is how you
       would quietly take over an account that already verifies, so a genuine
       re-enrolment has to go through an operator with dual control.

    The result is recorded as SELF_ASSERTED, which carries a claim ceiling - a
    weaker assertion than an officer checking a KTP, and the record says so.
    """
    peserta = await db.peserta.find_one({"firebase_uid": user.uid})
    if not peserta:
        raise ApiError(
            "PESERTA_NOT_FOUND",
            404,
            message="Akun ini belum tertaut dengan data peserta BPJS. "
            "Lengkapi nomor BPJS Anda terlebih dahulu.",
        )

    payloads = [await f.read() for f in frames] if frames else []
    result = await _run_enrollment(
        db,
        settings,
        peserta=peserta,
        payloads=payloads,
        assurance=enrollment_service.ASSURANCE_SELF,
        replace=False,
        actor=user.uid,
        request_id=request_id,
    )
    result["claim_ceiling"] = enrollment_service.ceiling_for(enrollment_service.ASSURANCE_SELF)
    return result


async def _run_enrollment(
    db,
    settings,
    *,
    peserta: dict,
    payloads: list[bytes],
    assurance: str,
    replace: bool,
    actor: str,
    request_id: str,
) -> dict:
    """Embed, check consistency, run the dedup gate, then activate the template.

    Shared by both enrolment paths on purpose: the security-critical steps - the
    1:N gate above all - must be impossible to reach by a route that skips them.
    """
    engine = face_engine.get_engine()
    if engine is None:
        raise ApiError("MODEL_UNAVAILABLE", 503, details={"reason": face_engine.load_error()})

    active = await db.biometric_templates.find_one(
        {"peserta_id": peserta["_id"], "modality": "face", "status": "active"}
    )
    # A seeded placeholder is not an enrolment; enrolling over it is the normal
    # first enrolment, not a replacement, so it needs no operator privilege.
    if active and not replace and not matcher.is_placeholder(active):
        raise ApiError("ALREADY_ENROLLED", 409, details={"template_id": str(active["_id"])})

    if not payloads:
        raise ApiError("NO_FRAMES", 400)

    embeddings, qualities = await run_in_threadpool(_embed_all, engine, payloads)
    if not embeddings:
        raise ApiError("NO_FACE_DETECTED", 400, details={"frames": len(payloads)})

    if len(embeddings) >= 2:
        pairs = [
            rotation.cosine(embeddings[i], embeddings[j])
            for i in range(len(embeddings))
            for j in range(i + 1, len(embeddings))
        ]
        worst = min(pairs)
        if worst < ENROLL_CONSISTENCY_MIN:
            raise ApiError(
                "ENROLL_FRAMES_INCONSISTENT",
                400,
                details={
                    "min_pairwise_cosine": round(worst, 4),
                    "required": ENROLL_CONSISTENCY_MIN,
                },
            )

    mean = enrollment_service.normalized_mean(embeddings)

    # ----------------------------------------------------------------- #
    # THE GATE. Sweep before activating anything.
    # ----------------------------------------------------------------- #
    rot = database.get_rotation()
    request = await enrollment_service.create_request(
        db,
        no_bpjs=peserta["no_bpjs"],
        assurance=assurance,
        staff=None,
        faskes_id=(peserta.get("faskes_tingkat1") or {}).get("faskes_id"),
    )
    dedup = await enrollment_service.run_dedup_gate(
        db,
        rot,
        mean,
        request_id=request["_id"],
        peserta_id=peserta["_id"],
        threshold=settings.enrollment_dedup_threshold,
    )
    if not dedup.passed:
        await enrollment_service.raise_duplicate_signal(
            db, request_id=request["_id"], no_bpjs=peserta["no_bpjs"], outcome=dedup
        )
        crypto.wipe(mean)
        raise ApiError(
            "DUPLICATE_FACE",
            409,
            message="Wajah ini sudah terdaftar atas peserta lain. "
            "Pendaftaran ditolak dan dilaporkan untuk ditinjau.",
            details={
                "matches": len(dedup.hits),
                "top_score": dedup.top_score,
                "enrollment_request_id": str(request["_id"]),
            },
        )

    await enrollment_service.mark_pending_approval(
        db, request_id=request["_id"], quality=qualities[0] if qualities else {}
    )

    now = datetime.now(UTC)
    if active:
        await db.biometric_templates.update_one(
            {"_id": active["_id"]}, {"$set": {"status": "superseded", "revoked_at": now}}
        )

    template_id = (
        await db.biometric_templates.insert_one(
            {
                "peserta_id": peserta["_id"],
                "modality": "face",
                "status": "active",
                "created_at": now,
            }
        )
    ).inserted_id

    kek = database.get_kek()
    aad = crypto.build_aad(peserta["_id"], template_id, 1)

    await db.biometric_templates.update_one(
        {"_id": template_id},
        {
            "$set": {
                "version": 1,
                "model": {
                    "name": settings.face_rec_model.stem,
                    "dim": int(mean.shape[0]),
                    "normalized": True,
                },
                "enc": crypto.encrypt_embedding(kek, mean, aad),
                "search_vector": rotation.apply_rotation(rot, mean).tolist(),
                "rotation_id": rotation.ROTATION_ID,
                "quality": qualities[0] if qualities else {},
                "enroll_meta": {
                    "frames_used": len(embeddings),
                    "frames_submitted": len(payloads),
                    "request_id": request_id,
                    "actor": actor,
                },
                "assurance": assurance,
                "enrollment_request_id": request["_id"],
                "revoked_at": None,
                "schema_version": 1,
            }
        },
    )
    await enrollment_service.attach_template(
        db, request_id=request["_id"], template_id=template_id, peserta_id=peserta["_id"]
    )
    await db.enrollment_requests.update_one(
        {"_id": request["_id"]},
        {"$set": {"status": enrollment_service.STATUS_APPROVED, "decided_at": now}},
    )
    await db.peserta.update_one(
        {"_id": peserta["_id"]},
        {"$set": {"biometric_enrolled": True, "biometric_enrolled_at": now}},
    )
    await audit.record(
        db,
        who=actor,
        what="enroll_face",
        peserta_id=peserta["_id"],
        purpose="pendaftaran_biometrik",
    )

    # The plaintext mean never leaves this function.
    crypto.wipe(mean)

    return {
        "status": "ok",
        "template_id": str(template_id),
        "peserta_id": str(peserta["_id"]),
        "frames_used": len(embeddings),
        "replaced": bool(active),
        "quality": qualities[0] if qualities else {},
        "assurance": assurance,
        "enrollment_request_id": str(request["_id"]),
        "dedup": {
            "passed": True,
            "candidates_checked": dedup.checked,
            "top_score": dedup.top_score,
        },
    }


def _embed_all(engine: face_engine.FaceEngine, payloads: list[bytes]):
    """CPU-bound; runs in a worker thread so the event loop stays free."""
    embeddings, qualities = [], []
    for raw in payloads:
        try:
            img = images.decode(raw)
        except ValueError:
            continue
        faces = engine.detect(img)
        if len(faces) != 1:
            continue
        face = faces[0]
        embeddings.append(engine.embed(img, face.kps))
        blur, bright = images.blur_variance(img), images.brightness(img)
        qualities.append(
            {
                "det_score": round(face.det_score, 4),
                "blur_var": round(blur, 1),
                "brightness": round(bright, 1),
                "face_px": int(face.short_side),
            }
        )
    return embeddings, qualities


@router.post("/face/probe")
async def probe_face(
    db: DbDep,
    settings: SettingsDep,
    _: OperatorDep,
    frames: list[UploadFile] = File(...),
) -> dict:
    """Score a photo against every enrolled template. Operator diagnostics only.

    This is the tool for answering "did my enrolment actually work?" without
    running a whole verification session. It also surfaces collisions: if one
    face matches two different participants, that is the FACE_COLLISION fraud
    case, and it is far better to discover it here than mid-demo.

    Runs on the rotated search vectors, so nothing is decrypted.
    """
    engine = face_engine.get_engine()
    if engine is None:
        raise ApiError("MODEL_UNAVAILABLE", 503, details={"reason": face_engine.load_error()})
    if not frames:
        raise ApiError("NO_FRAMES", 400)

    payloads = [await f.read() for f in frames]
    embeddings, qualities = await run_in_threadpool(_embed_all, engine, payloads)
    if not embeddings:
        raise ApiError("NO_FACE_DETECTED", 400, details={"frames": len(payloads)})

    probe = rotation.l2_normalize(np.mean(np.stack(embeddings), axis=0))
    rot = database.get_rotation()

    # threshold 0.0 so the caller sees the full ranking, including near misses -
    # a score of 0.38 against yourself is much more useful to know than silence.
    hits = await matcher.sweep_collisions(db, rot, probe, threshold=0.0)
    crypto.wipe(probe)

    top = hits[:10]
    names: dict = {}
    if top:
        async for doc in db.peserta.find(
            {"_id": {"$in": [h["peserta_id"] for h in top]}},
            {"nama_lengkap": 1, "no_bpjs": 1},
        ):
            names[doc["_id"]] = doc

    return {
        "status": "ok",
        "frames_used": len(embeddings),
        "quality": qualities[0] if qualities else {},
        "thresholds": {
            "accept": settings.face_match_accept,
            "review": settings.face_match_review,
            "collision": settings.face_collision_threshold,
        },
        "matches": [
            {
                "peserta_id": str(h["peserta_id"]),
                "nama": (names.get(h["peserta_id"]) or {}).get("nama_lengkap"),
                "no_bpjs": (names.get(h["peserta_id"]) or {}).get("no_bpjs"),
                "score": h["score"],
                "verdict": matcher.decide(h["score"], settings.face_match_accept, settings.face_match_review),
            }
            for h in top
        ],
    }


@router.delete("/face/{peserta_id}", response_model=OkResponse)
async def revoke_face(peserta_id: str, db: DbDep, _: OperatorDep) -> OkResponse:
    """Right to erasure. Zeroes both the ciphertext and the search vector so the
    biometric is genuinely gone, not just flagged."""
    try:
        oid = ObjectId(peserta_id)
    except Exception as exc:
        raise ApiError("PESERTA_NOT_FOUND", 404) from exc

    now = datetime.now(UTC)
    result = await db.biometric_templates.update_many(
        {"peserta_id": oid, "modality": "face", "status": "active"},
        {
            "$set": {
                "status": "revoked",
                "revoked_at": now,
                "search_vector": [],
                "enc.ciphertext": b"",
                "enc.dek_wrapped": b"",
            }
        },
    )
    await db.peserta.update_one({"_id": oid}, {"$set": {"biometric_enrolled": False}})
    await audit.record(
        db, who="operator", what="revoke_face", peserta_id=oid, purpose="penghapusan_biometrik"
    )
    log.info("revoked %d face templates for peserta %s", result.modified_count, peserta_id)
    return OkResponse()


@router.post("/device")
async def enroll_device(
    payload: dict,
    db: DbDep,
    settings: SettingsDep,
    user: CurrentUserDep,
) -> dict:
    """Register a device public key (Tier B) or shared secret hash (Tier A).

    Tier A stores a 32-byte secret so the server can verify an HMAC. That secret
    IS extractable in principle, which is exactly why sessions verified this way
    are recorded as security_level SOFTWARE and raise a fraud signal.

    Requires a signed-in user, and the record is stamped with THAT uid, not one
    from the body: an unauthenticated upsert would let anyone who learned a
    device_uid replace its secret with their own and then sign as that device.
    """
    device_uid = payload.get("device_uid")
    if not device_uid or len(device_uid) < 16:
        raise ApiError("VALIDATION_ERROR", 422, details={"field": "device_uid"})

    method = payload.get("method", "hmac_sha256_shared_secret")
    now = datetime.now(UTC)

    doc: dict = {
        "device_uid": device_uid,
        "firebase_uid": user.uid,
        "platform": payload.get("platform", "android"),
        "last_seen": now,
        "blocked": False,
    }
    # Only write optional fields the client actually sent; storing explicit nulls
    # adds nothing and forces every reader to handle a third state.
    for field in ("os_version", "model", "app_version"):
        if payload.get(field):
            doc[field] = str(payload[field])

    if method == "android_keystore_ec_p256":
        pub = payload.get("public_key_der_b64")
        if not pub:
            raise ApiError("VALIDATION_ERROR", 422, details={"field": "public_key_der_b64"})
        public_key_der = base64.b64decode(pub)
        # Refuse anything that is not an EC P-256 SubjectPublicKeyInfo now,
        # rather than at the first signature check.
        probe = attestation.verify_ec_p256(payload="x", signature=b"", public_key_der=public_key_der)
        if probe.error_code == "KEY_MISMATCH":
            raise ApiError(
                "VALIDATION_ERROR", 422, details={"field": "public_key_der_b64", **(probe.detail or {})}
            )

        chain = [base64.b64decode(c) for c in payload.get("attestation_chain_b64") or []]
        evaluated = attestation.evaluate_attestation_chain(
            chain, public_key_der=public_key_der, expected_challenge=device_uid.encode("utf-8")
        )
        # user_auth_required comes from the TEE-enforced authorization list in
        # the certificate, not from the app. A key the hardware will sign with
        # WITHOUT a fingerprint is not a second factor, whatever its level.
        evaluated["client_security_level"] = payload.get("client_security_level")
        if evaluated["user_auth_required"] is False:
            evaluated["security_level"] = "SOFTWARE"
            evaluated["error"] = "key is usable without user authentication"

        doc["public_key_der"] = public_key_der
        doc["key_alias"] = payload.get("key_alias", "identicare_bpjs_v1")
        # "hardware" only when the certificate chain says so about THIS key.
        # A keystore key without a usable chain is still stronger than an HMAC
        # secret (it cannot be exported), but the server has no evidence of
        # that, so it does not get the label.
        doc["trust_level"] = "hardware" if evaluated["security_level"] in ("TEE", "STRONGBOX") else "software"
        doc["attestation"] = evaluated
        log.info(
            "device %s keystore enrolment: level=%s key_matches=%s challenge_ok=%s chain=%d",
            device_uid[:12],
            evaluated["security_level"],
            evaluated["key_matches"],
            evaluated["challenge_ok"],
            evaluated["chain_length"],
        )
    else:
        secret = payload.get("shared_secret_b64")
        if not secret:
            raise ApiError("VALIDATION_ERROR", 422, details={"field": "shared_secret_b64"})
        kek = database.get_kek()
        aad = crypto.build_aad(device_uid, "device_secret", 1)
        doc["secret_enc"] = crypto.encrypt_blob(kek, base64.b64decode(secret), aad)
        doc["trust_level"] = "software"
        doc["attestation"] = {"chain_verified": False, "security_level": "SOFTWARE"}

    existing = await db.devices.find_one({"device_uid": device_uid}, {"_id": 1})
    if existing:
        await db.devices.update_one({"_id": existing["_id"]}, {"$set": doc})
        device_id = existing["_id"]
    else:
        doc["first_seen"] = now
        doc["peserta_ids"] = []
        device_id = (await db.devices.insert_one(doc)).inserted_id

    return {
        "status": "ok",
        "device_id": str(device_id),
        "trust_level": doc["trust_level"],
        "security_level": doc["attestation"]["security_level"],
    }
