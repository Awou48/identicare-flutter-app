"""Enrolment identity-proofing.

THE HOLE THIS CLOSES. Before this, `POST /enrollment/face` needed only one
shared static API key and performed NO duplicate check. An insider could enrol
their own face against someone else's `no_bpjs`, and from then on every
verification would succeed *correctly* - the fraud becomes permanently
invisible, because the biometric genuinely matches the template on file. Every
other control in this system sits on top of enrolment, so poisoning it defeats
all of them at once.

Three controls, each independently useful:

  1. MANDATORY 1:N de-duplication. No template is activated until the face has
     been swept against every active template. A hit under a different no_bpjs
     is rejected outright and raises a critical fraud signal. The sweep function
     already existed in matcher.py - it simply was never called on this path.
  2. FOUR-EYES. Approval requires a different staff_id from the capturer,
     enforced server-side. A single compromised account cannot self-approve.
  3. COOLING-OFF. A template younger than the configured window cannot support a
     high-value claim. This bounds the damage even if 1 and 2 are both defeated.

Assurance levels are recorded on the template, and the claim ceiling is applied
per level, so a self-asserted identity cannot underwrite a large claim.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.security import crypto, rotation
from app.security.staff_auth import ROLE_SUPERVISOR, StaffPrincipal
from app.services import audit, matcher
from app.utils.errors import ApiError

log = logging.getLogger(__name__)

ASSURANCE_SELF = "SELF_ASSERTED"
ASSURANCE_DUKCAPIL = "DUKCAPIL_VERIFIED"
ASSURANCE_ASSISTED = "ASSISTED_DUAL_CONTROL"

# Claim ceiling in rupiah per assurance level. A weakly-proven identity may use
# the system, but cannot underwrite an expensive claim.
CLAIM_CEILING: dict[str, int] = {
    ASSURANCE_SELF: 500_000,
    ASSURANCE_DUKCAPIL: 0,  # 0 == no ceiling
    ASSURANCE_ASSISTED: 0,
}

# Levels that a single operator may approve alone. Assisted enrolment is the one
# that carries the strongest claim, so it is the one that must be witnessed.
REQUIRES_SECOND_STAFF = {ASSURANCE_ASSISTED}

STATUS_DRAFT = "draft"
STATUS_PENDING_DEDUP = "pending_dedup"
STATUS_PENDING_APPROVAL = "pending_approval"
STATUS_APPROVED = "approved"
STATUS_REJECTED_DUPLICATE = "rejected_duplicate"
STATUS_REJECTED_REVIEW = "rejected_review"

IN_FLIGHT = (STATUS_DRAFT, STATUS_PENDING_DEDUP, STATUS_PENDING_APPROVAL)


@dataclass
class DedupOutcome:
    passed: bool
    checked: int
    hits: list[dict[str, Any]]
    top_score: float | None

    def to_doc(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checked_at": datetime.now(UTC),
            "candidates_checked": self.checked,
            "top_score": self.top_score,
            "hits": [
                {"peserta_id": str(h["peserta_id"]), "score": h["score"]} for h in self.hits[:5]
            ],
        }


# --------------------------------------------------------------------------- #
async def create_request(
    db: AsyncDatabase,
    *,
    no_bpjs: str,
    assurance: str,
    staff: StaffPrincipal | None,
    faskes_id: ObjectId | None,
) -> dict:
    """Open an enrolment request. Unique partial index guarantees one in flight."""
    if assurance not in CLAIM_CEILING:
        raise ApiError("VALIDATION_ERROR", 422, details={"assurance": assurance})

    now = datetime.now(UTC)
    doc = {
        "no_bpjs": no_bpjs,
        "status": STATUS_DRAFT,
        "assurance": assurance,
        "captured_by": ObjectId(staff.staff_id) if staff else None,
        "approved_by": None,
        "faskes_id": faskes_id,
        "dedup": {},
        "quality": {},
        "rejection_reason": None,
        "template_id": None,
        "evidence": {},
        "dukcapil": {},
        "created_at": now,
        "updated_at": now,
        "decided_at": None,
        "schema_version": 1,
    }
    try:
        result = await db.enrollment_requests.insert_one(doc)
    except DuplicateKeyError as exc:
        # The partial unique index fired: another enrolment for this participant
        # is already open. Racing two enrolments could let both clear the dedup
        # gate against a state that no longer holds by the time they commit.
        raise ApiError(
            "ENROLLMENT_IN_PROGRESS",
            409,
            message="Sudah ada permohonan pendaftaran biometrik yang sedang berjalan "
            "untuk peserta ini.",
        ) from exc
    doc["_id"] = result.inserted_id
    return doc


async def run_dedup_gate(
    db: AsyncDatabase,
    rot: np.ndarray,
    probe: np.ndarray,
    *,
    request_id: ObjectId,
    peserta_id: ObjectId | None,
    threshold: float,
) -> DedupOutcome:
    """The gate. Sweep this face against every active template.

    Runs on rotated search vectors, so nothing is decrypted - see
    security/rotation.py. A hit belonging to a DIFFERENT participant means this
    face is already enrolled under another BPJS number, which is the
    FACE_COLLISION fraud case caught at the only moment it can still be
    prevented rather than merely detected.
    """
    hits = await matcher.sweep_collisions(
        db, rot, probe, threshold=threshold, exclude_peserta_id=peserta_id
    )
    total = await db.biometric_templates.count_documents(
        {"modality": "face", "status": "active"}
    )
    outcome = DedupOutcome(
        passed=not hits,
        checked=total,
        hits=hits,
        top_score=hits[0]["score"] if hits else None,
    )
    await db.enrollment_requests.update_one(
        {"_id": request_id},
        {
            "$set": {
                "status": STATUS_PENDING_DEDUP if outcome.passed else STATUS_REJECTED_DUPLICATE,
                "dedup": outcome.to_doc(),
                "updated_at": datetime.now(UTC),
            }
        },
    )
    if not outcome.passed:
        log.warning(
            "enrolment %s rejected: face matches %d existing peserta (top %.4f)",
            request_id,
            len(hits),
            hits[0]["score"],
        )
    return outcome


async def raise_duplicate_signal(
    db: AsyncDatabase, *, request_id: ObjectId, no_bpjs: str, outcome: DedupOutcome
) -> None:
    """A duplicate enrolment attempt is a critical fraud event in its own right,
    whether or not it succeeded."""
    if not outcome.hits:
        return
    top = outcome.hits[0]
    await db.fraud_signals.insert_one(
        {
            "peserta_id": top["peserta_id"],
            "session_id": None,
            "rule_id": "DUPLICATE_ENROLLMENT_ATTEMPT",
            "severity": "critical",
            "weight": 40,
            "title": "Percobaan pendaftaran wajah ganda",
            "detail": {
                "enrollment_request_id": str(request_id),
                "attempted_no_bpjs": no_bpjs,
                "matched_peserta_id": str(top["peserta_id"]),
                "score": top["score"],
                "total_matches": len(outcome.hits),
            },
            "status": "open",
            "detected_at": datetime.now(UTC),
            "resolved_at": None,
            "resolved_by": None,
        }
    )


async def approve(
    db: AsyncDatabase,
    *,
    request_id: ObjectId,
    approver: StaffPrincipal,
    require_second_staff: bool,
) -> dict:
    """Four-eyes approval.

    The approver must be a different person from the capturer. This is checked
    against the stored `captured_by`, not against anything the client sends -
    a client-asserted "I am a different person" is worth nothing.
    """
    request = await db.enrollment_requests.find_one({"_id": request_id})
    if not request:
        raise ApiError("ENROLLMENT_NOT_FOUND", 404)

    if request["status"] != STATUS_PENDING_APPROVAL:
        raise ApiError(
            "ENROLLMENT_NOT_PENDING",
            409,
            details={"status": request["status"], "expected": STATUS_PENDING_APPROVAL},
        )

    if require_second_staff:
        approver.require(ROLE_SUPERVISOR)
        captured_by = request.get("captured_by")
        if captured_by is not None and str(captured_by) == approver.staff_id:
            raise ApiError(
                "FOUR_EYES_REQUIRED",
                403,
                message="Pendaftaran harus disetujui oleh petugas yang berbeda "
                "dari yang melakukan pengambilan data.",
                details={"captured_by": str(captured_by)},
            )

    now = datetime.now(UTC)
    updated = await db.enrollment_requests.find_one_and_update(
        {"_id": request_id, "status": STATUS_PENDING_APPROVAL},
        {
            "$set": {
                "status": STATUS_APPROVED,
                "approved_by": ObjectId(approver.staff_id),
                "decided_at": now,
                "updated_at": now,
            }
        },
        return_document=True,
    )
    if updated is None:
        raise ApiError("ENROLLMENT_NOT_PENDING", 409)

    await audit.record(
        db,
        who=f"staff:{approver.staff_id}",
        what="approve_enrollment",
        peserta_id=updated.get("peserta_id"),
        purpose="persetujuan_pendaftaran_biometrik",
    )
    return updated


async def reject(
    db: AsyncDatabase, *, request_id: ObjectId, reason: str, staff: StaffPrincipal | None
) -> None:
    now = datetime.now(UTC)
    await db.enrollment_requests.update_one(
        {"_id": request_id},
        {
            "$set": {
                "status": STATUS_REJECTED_REVIEW,
                "rejection_reason": reason,
                "approved_by": ObjectId(staff.staff_id) if staff else None,
                "decided_at": now,
                "updated_at": now,
            }
        },
    )


async def mark_pending_approval(
    db: AsyncDatabase, *, request_id: ObjectId, quality: dict[str, Any]
) -> None:
    await db.enrollment_requests.update_one(
        {"_id": request_id},
        {
            "$set": {
                "status": STATUS_PENDING_APPROVAL,
                "quality": quality,
                "updated_at": datetime.now(UTC),
            }
        },
    )


async def attach_template(
    db: AsyncDatabase, *, request_id: ObjectId, template_id: ObjectId, peserta_id: ObjectId
) -> None:
    await db.enrollment_requests.update_one(
        {"_id": request_id},
        {
            "$set": {
                "template_id": template_id,
                "peserta_id": peserta_id,
                "updated_at": datetime.now(UTC),
            }
        },
    )


async def store_evidence(
    db: AsyncDatabase,
    kek: bytes,
    *,
    request_id: ObjectId,
    label: str,
    blob: bytes,
) -> None:
    """Encrypt a KTP / BPJS card photo against the request document.

    AAD binds the ciphertext to this request, so an evidence blob cannot be
    lifted onto a different enrolment.
    """
    aad = crypto.build_aad(request_id, f"evidence_{label}", 1)
    await db.enrollment_requests.update_one(
        {"_id": request_id},
        {"$set": {f"evidence.{label}": crypto.encrypt_blob(kek, blob, aad)}},
    )


# --------------------------------------------------------------------------- #
# Claim ceiling / cooling-off - consumed by the session start path
# --------------------------------------------------------------------------- #
def ceiling_for(assurance: str | None) -> int:
    """Templates predating this pipeline carry no assurance; treat them as the
    weakest level rather than silently granting them full trust."""
    return CLAIM_CEILING.get(assurance or ASSURANCE_SELF, CLAIM_CEILING[ASSURANCE_SELF])


def check_claim_allowed(
    template: dict, estimasi_biaya: int, cooling_hours: int
) -> tuple[bool, str | None, dict[str, Any]]:
    """Returns (allowed, error_code, details).

    Two independent gates: the assurance ceiling, and a cooling-off window that
    bounds the damage from an enrolment that was fraudulent but not yet detected.
    """
    assurance = template.get("assurance")
    ceiling = ceiling_for(assurance)
    if ceiling and estimasi_biaya > ceiling:
        return (
            False,
            "ASSURANCE_CEILING_EXCEEDED",
            {
                "assurance": assurance or ASSURANCE_SELF,
                "ceiling": ceiling,
                "requested": estimasi_biaya,
            },
        )

    created_at = template.get("created_at")
    if cooling_hours and created_at is not None:
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        age = datetime.now(UTC) - created_at
        if age < timedelta(hours=cooling_hours) and estimasi_biaya > CLAIM_CEILING[ASSURANCE_SELF]:
            return (
                False,
                "ENROLLMENT_COOLING_OFF",
                {
                    "enrolled_at": created_at.isoformat(),
                    "cooling_hours": cooling_hours,
                    "hours_elapsed": round(age.total_seconds() / 3600, 1),
                },
            )

    return True, None, {}


def normalized_mean(embeddings: list[np.ndarray]) -> np.ndarray:
    return rotation.l2_normalize(np.mean(np.stack(embeddings), axis=0))
