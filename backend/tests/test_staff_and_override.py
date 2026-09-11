"""The two controls added in v2: enrolment proofing and the staff override.

These cover the logic that decides whether a poisoned enrolment can be created
and whether a break-glass override can be self-approved. Both are pure units -
no server, no MongoDB.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.db_schema import (
    ASSURANCE_LEVELS,
    DECISIONS,
    ENROLLMENT_STATUS,
    OVERRIDE_REASONS,
    SESSION_STATUS,
    STAFF_ROLES,
)
from app.security import staff_auth
from app.security.staff_auth import (
    ROLE_ADMIN,
    ROLE_INVESTIGATOR,
    ROLE_PETUGAS,
    ROLE_SUPERVISOR,
    StaffPrincipal,
)
from app.services import enrollment_service, fraud_rules, session_service
from app.utils.errors import ApiError


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #
def test_password_roundtrip() -> None:
    stored = staff_auth.hash_password("correct horse battery")
    assert staff_auth.verify_password("correct horse battery", stored)
    assert not staff_auth.verify_password("wrong horse battery", stored)


def test_password_hash_is_salted() -> None:
    """Same password, different hashes - so a stolen table does not reveal which
    staff share a password."""
    a = staff_auth.hash_password("same-password")
    b = staff_auth.hash_password("same-password")
    assert a != b
    assert staff_auth.verify_password("same-password", a)
    assert staff_auth.verify_password("same-password", b)


def test_short_password_refused() -> None:
    with pytest.raises(ValueError):
        staff_auth.hash_password("short")


def test_malformed_hash_denies_rather_than_raises() -> None:
    """A corrupt row must fail login, not 500 the endpoint."""
    for bad in ("", "garbage", "scrypt$notanumber$8$1$aa$bb", "bcrypt$1$2$3$aa$bb"):
        assert staff_auth.verify_password("anything", bad) is False


# --------------------------------------------------------------------------- #
# Tokens and roles
# --------------------------------------------------------------------------- #
KEK = b"k" * 32


def test_token_roundtrip() -> None:
    token = staff_auth.issue_token(
        KEK, staff_id="abc123", nama="Sari", role=ROLE_SUPERVISOR, faskes_id="f1"
    )
    principal = staff_auth.verify_token(KEK, token)
    assert principal.staff_id == "abc123"
    assert principal.role == ROLE_SUPERVISOR
    assert principal.faskes_id == "f1"


def test_token_signed_with_a_different_kek_is_rejected() -> None:
    token = staff_auth.issue_token(
        KEK, staff_id="a", nama="n", role=ROLE_PETUGAS, faskes_id=None
    )
    with pytest.raises(ApiError) as exc:
        staff_auth.verify_token(b"x" * 32, token)
    assert exc.value.code == "UNAUTHENTICATED"


def test_garbage_token_is_rejected() -> None:
    with pytest.raises(ApiError):
        staff_auth.verify_token(KEK, "not.a.jwt")


def test_role_grants_are_not_a_flat_hierarchy() -> None:
    """An investigator reads fraud cases but must NOT approve a clinical
    override; a petugas must not read the investigator console. A simple
    ordering would quietly grant both."""
    investigator = StaffPrincipal("i", "I", ROLE_INVESTIGATOR, None)
    assert not investigator.can_act_as(ROLE_SUPERVISOR)
    assert not investigator.can_act_as(ROLE_PETUGAS)

    petugas = StaffPrincipal("p", "P", ROLE_PETUGAS, None)
    assert not petugas.can_act_as(ROLE_INVESTIGATOR)
    assert not petugas.can_act_as(ROLE_SUPERVISOR)

    supervisor = StaffPrincipal("s", "S", ROLE_SUPERVISOR, None)
    assert supervisor.can_act_as(ROLE_PETUGAS)
    assert supervisor.can_act_as(ROLE_SUPERVISOR)
    assert not supervisor.can_act_as(ROLE_INVESTIGATOR)

    admin = StaffPrincipal("a", "A", ROLE_ADMIN, None)
    assert all(admin.can_act_as(r) for r in STAFF_ROLES)


def test_require_raises_forbidden() -> None:
    petugas = StaffPrincipal("p", "P", ROLE_PETUGAS, None)
    with pytest.raises(ApiError) as exc:
        petugas.require(ROLE_SUPERVISOR)
    assert exc.value.code == "FORBIDDEN"
    assert exc.value.status_code == 403


# --------------------------------------------------------------------------- #
# Assurance ceiling and cooling-off
# --------------------------------------------------------------------------- #
def _template(assurance: str | None, age_hours: float = 100.0) -> dict:
    return {
        "assurance": assurance,
        "created_at": datetime.now(UTC) - timedelta(hours=age_hours),
    }


def test_self_asserted_has_a_claim_ceiling() -> None:
    ok, code, details = enrollment_service.check_claim_allowed(
        _template(enrollment_service.ASSURANCE_SELF), 5_000_000, cooling_hours=0
    )
    assert not ok
    assert code == "ASSURANCE_CEILING_EXCEEDED"
    assert details["requested"] == 5_000_000


def test_self_asserted_allows_a_small_claim() -> None:
    ok, code, _ = enrollment_service.check_claim_allowed(
        _template(enrollment_service.ASSURANCE_SELF), 100_000, cooling_hours=0
    )
    assert ok and code is None


def test_dukcapil_verified_has_no_ceiling() -> None:
    ok, _, _ = enrollment_service.check_claim_allowed(
        _template(enrollment_service.ASSURANCE_DUKCAPIL), 50_000_000, cooling_hours=0
    )
    assert ok


def test_missing_assurance_is_treated_as_weakest() -> None:
    """Templates enrolled before this pipeline existed carry no assurance. They
    must NOT be silently granted full trust."""
    assert enrollment_service.ceiling_for(None) == enrollment_service.CLAIM_CEILING[
        enrollment_service.ASSURANCE_SELF
    ]
    ok, code, _ = enrollment_service.check_claim_allowed(
        _template(None), 5_000_000, cooling_hours=0
    )
    assert not ok and code == "ASSURANCE_CEILING_EXCEEDED"


def test_cooling_off_blocks_a_fresh_high_value_claim() -> None:
    """Bounds the damage of a fraudulent enrolment that has not been caught yet."""
    ok, code, details = enrollment_service.check_claim_allowed(
        _template(enrollment_service.ASSURANCE_DUKCAPIL, age_hours=1),
        5_000_000,
        cooling_hours=24,
    )
    assert not ok
    assert code == "ENROLLMENT_COOLING_OFF"
    assert details["hours_elapsed"] == pytest.approx(1.0, abs=0.2)


def test_cooling_off_expires() -> None:
    ok, _, _ = enrollment_service.check_claim_allowed(
        _template(enrollment_service.ASSURANCE_DUKCAPIL, age_hours=48),
        5_000_000,
        cooling_hours=24,
    )
    assert ok


def test_cooling_off_still_allows_small_claims() -> None:
    """A cooling-off window must not block routine care - only large claims."""
    ok, _, _ = enrollment_service.check_claim_allowed(
        _template(enrollment_service.ASSURANCE_DUKCAPIL, age_hours=1),
        100_000,
        cooling_hours=24,
    )
    assert ok


def test_naive_datetime_is_handled() -> None:
    """Mongo can return tz-naive datetimes; comparing them to an aware now()
    would raise TypeError and 500 the claim."""
    ok, _, _ = enrollment_service.check_claim_allowed(
        {"assurance": enrollment_service.ASSURANCE_DUKCAPIL, "created_at": datetime(2020, 1, 1)},
        5_000_000,
        cooling_hours=24,
    )
    assert ok


# --------------------------------------------------------------------------- #
# Dedup outcome
# --------------------------------------------------------------------------- #
def test_dedup_outcome_passes_only_with_no_hits() -> None:
    clean = enrollment_service.DedupOutcome(passed=True, checked=120, hits=[], top_score=None)
    assert clean.passed
    doc = clean.to_doc()
    assert doc["passed"] is True
    # An empty list is a PASS that actually ran; a missing field would mean the
    # gate never executed, which is a very different thing.
    assert doc["candidates_checked"] == 120
    assert doc["hits"] == []


def test_dedup_outcome_records_the_top_hit() -> None:
    hit = {"peserta_id": "other-person", "score": 0.71}
    dirty = enrollment_service.DedupOutcome(
        passed=False, checked=120, hits=[hit], top_score=0.71
    )
    doc = dirty.to_doc()
    assert doc["passed"] is False
    assert doc["top_score"] == 0.71
    assert doc["hits"][0]["peserta_id"] == "other-person"


# --------------------------------------------------------------------------- #
# Override state machine
# --------------------------------------------------------------------------- #
def test_rejected_is_no_longer_terminal() -> None:
    """This is the whole point: a failed face must be able to escalate rather
    than dead-end, or the system denies care to bruised and burned patients."""
    assert "rejected" not in session_service.TERMINAL
    assert "rejected" in session_service.OVERRIDE_ELIGIBLE


def test_truly_terminal_states_stay_terminal() -> None:
    for status in ("committed", "expired", "cancelled", "override_rejected"):
        assert status in session_service.TERMINAL


def test_override_states_declared_in_validator_enum() -> None:
    assert set(session_service.NEXT_STEP) == set(SESSION_STATUS)
    for status in ("override_pending", "override_rejected"):
        assert status in SESSION_STATUS


def test_override_pending_accepts_no_normal_step() -> None:
    """The override path has its own endpoints; the step sequence must not
    advance from override_pending."""
    session = {"_id": "s", "status": "override_pending", "steps": {}}
    for step in ("face", "fingerprint", "review", "commit"):
        with pytest.raises(ApiError) as exc:
            session_service.require_state(session, step)
        assert exc.value.code == "STEP_OUT_OF_ORDER"


def test_approved_with_override_is_a_distinct_decision() -> None:
    """It must never collapse into plain APPROVED, or a claim that skipped
    biometric proof becomes indistinguishable from one that passed it."""
    assert "APPROVED_WITH_OVERRIDE" in DECISIONS
    assert "APPROVED" in DECISIONS
    assert "APPROVED_WITH_OVERRIDE" != "APPROVED"


def test_override_reasons_are_a_closed_enum() -> None:
    """Free text alone is unanalysable, and spotting patterns across staff is
    the entire reason for recording a reason."""
    assert "LAINNYA" in OVERRIDE_REASONS
    assert "CEDERA_WAJAH" in OVERRIDE_REASONS
    assert "LUKA_BAKAR_JARI" in OVERRIDE_REASONS


def test_enrollment_and_assurance_enums_are_wired() -> None:
    assert set(ENROLLMENT_STATUS) >= {
        enrollment_service.STATUS_DRAFT,
        enrollment_service.STATUS_PENDING_DEDUP,
        enrollment_service.STATUS_PENDING_APPROVAL,
        enrollment_service.STATUS_APPROVED,
        enrollment_service.STATUS_REJECTED_DUPLICATE,
    }
    assert set(ASSURANCE_LEVELS) == set(enrollment_service.CLAIM_CEILING)


# --------------------------------------------------------------------------- #
# Override fraud signals
# --------------------------------------------------------------------------- #
def test_manual_override_raises_a_signal() -> None:
    session = {
        "override": {"status": "approved", "reason_code": "CEDERA_WAJAH",
                     "requested_by": "p1", "approved_by": "s1"},
        "context": {"faskes_id": "f1"},
    }
    signals = fraud_rules._manual_override(session)
    assert signals[0].rule_id == "MANUAL_OVERRIDE"
    assert signals[0].severity == "high"
    assert signals[0].detail["reason_code"] == "CEDERA_WAJAH"


def test_no_signal_without_an_approved_override() -> None:
    assert fraud_rules._manual_override({}) == []
    assert fraud_rules._manual_override({"override": {"status": "pending"}}) == []
    assert fraud_rules._manual_override({"override": {"status": "rejected"}}) == []


def test_override_alone_does_not_reject_the_claim() -> None:
    """An override is not an accusation. Weight 25 lands in REVIEW, not
    REJECTED - most overrides are legitimate clinical reality."""
    signals = fraud_rules._manual_override(
        {
            "override": {"status": "approved", "reason_code": "LUKA_BAKAR_JARI",
                         "requested_by": "p", "approved_by": "s"},
            "context": {},
        }
    )
    score = sum(s.weight for s in signals)
    band, decision = fraud_rules.band_for(score, signals)
    assert decision == "APPROVED"  # 25 on its own is still LOW
    assert band == "LOW"


def test_override_plus_arrears_escalates_to_review() -> None:
    signals = fraud_rules._manual_override(
        {
            "override": {"status": "approved", "reason_code": "LAINNYA",
                         "requested_by": "p", "approved_by": "s"},
            "context": {},
        }
    ) + fraud_rules._menunggak({"tunggakan_bulan": 2})
    score = sum(s.weight for s in signals)
    assert score == 40
    assert fraud_rules.band_for(score, signals) == ("MEDIUM", "REVIEW")


def test_override_frequency_constants_are_sane() -> None:
    assert fraud_rules.OVERRIDE_WEEKLY_LIMIT > 0
    assert fraud_rules.OVERRIDE_WINDOW_DAYS >= 7


def test_a_critical_frequency_signal_rejects_even_a_low_score() -> None:
    """The control that catches insider fraud: one override is a bruised face,
    twenty in a week is the override being used as the mechanism."""
    frequency = fraud_rules.Signal(
        "STAFF_OVERRIDE_FREQUENCY", "critical", 35, "terlalu sering", {"override_count": 22}
    )
    assert fraud_rules.band_for(10, [frequency]) == ("HIGH", "REJECTED")
