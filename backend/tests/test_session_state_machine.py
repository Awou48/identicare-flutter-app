"""State machine, fraud rules, attestation and liveness scoring.

Pure unit tests - no server, no MongoDB. These cover the logic that decides
whether a BPJS claim is approved, which is the part that must not regress
silently.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.security import attestation
from app.services import fraud_rules, liveness, matcher, session_service
from app.services.face_engine import Face
from app.utils.errors import ApiError
from app.utils.geo import haversine_km, implied_speed_kmh


# --------------------------------------------------------------------------- #
# State machine
# --------------------------------------------------------------------------- #
def _session(status: str) -> dict:
    return {"_id": "s1", "status": status, "steps": {}}


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("created", "face"),
        ("face_passed", "fingerprint"),
        ("fingerprint_passed", "review"),
        ("reviewed", "commit"),
        ("committed", None),
        ("rejected", None),
        ("expired", None),
        ("cancelled", None),
    ],
)
def test_next_step_mapping(status: str, expected: str | None) -> None:
    assert session_service.NEXT_STEP[status] == expected


def test_require_state_allows_the_expected_step() -> None:
    session_service.require_state(_session("created"), "face")
    session_service.require_state(_session("face_passed"), "fingerprint")
    session_service.require_state(_session("fingerprint_passed"), "review")
    session_service.require_state(_session("reviewed"), "commit")


def test_cannot_skip_the_face_step() -> None:
    """The attack this guard exists for: jump straight to fingerprint, or to
    review, and never submit a face at all."""
    for step in ("fingerprint", "review", "commit"):
        with pytest.raises(ApiError) as exc:
            session_service.require_state(_session("created"), step)
        assert exc.value.code == "STEP_OUT_OF_ORDER"
        assert exc.value.status_code == 409


def test_cannot_replay_a_completed_step() -> None:
    with pytest.raises(ApiError) as exc:
        session_service.require_state(_session("face_passed"), "face")
    assert exc.value.code == "STEP_OUT_OF_ORDER"


def test_terminal_states_accept_nothing() -> None:
    for status in session_service.TERMINAL:
        for step in ("face", "fingerprint", "review", "commit"):
            with pytest.raises(ApiError):
                session_service.require_state(_session(status), step)


def test_every_status_is_in_the_validator_enum() -> None:
    from app.db_schema import SESSION_STATUS

    assert set(session_service.NEXT_STEP) == set(SESSION_STATUS)


def test_tokens_and_nonces_are_unguessable() -> None:
    tokens = {session_service.new_token() for _ in range(200)}
    nonces = {session_service.new_nonce() for _ in range(200)}
    assert len(tokens) == 200 and len(nonces) == 200
    assert all(len(t) == 64 for t in tokens)


def test_receipt_number_format() -> None:
    when = datetime(2026, 9, 8, tzinfo=UTC)
    assert session_service.receipt_number(123, when) == "VRF-20260908-000123"


def test_public_view_hides_the_session_token() -> None:
    """The client already holds the token; echoing it back only widens the blast
    radius of any log or crash report that captures a response body."""
    session = {
        "_id": "abc",
        "session_token": "SECRET-TOKEN",
        "status": "face_passed",
        "expires_at": datetime.now(UTC),
        "nonce": "SECRET-NONCE",
        "steps": {"face": {"status": "passed", "template_id": "tmpl1"}},
        "risk": {},
        "result": None,
    }
    view = session_service.public_view(session)
    flat = str(view)
    assert "SECRET-TOKEN" not in flat
    assert "SECRET-NONCE" not in flat
    assert "tmpl1" not in flat
    assert view["current_step"] == "fingerprint"


# --------------------------------------------------------------------------- #
# Matching decision
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("score", "expected"),
    [(0.90, "accept"), (0.42, "accept"), (0.41, "review"), (0.30, "review"),
     (0.29, "reject"), (-0.5, "reject")],
)
def test_decide_thresholds(score: float, expected: str) -> None:
    assert matcher.decide(score, 0.42, 0.30) == expected


# --------------------------------------------------------------------------- #
# Fraud scoring
# --------------------------------------------------------------------------- #
def _signal(rule_id: str, severity: str, weight: int) -> fraud_rules.Signal:
    return fraud_rules.Signal(rule_id, severity, weight, "t", {})


def test_bands() -> None:
    assert fraud_rules.band_for(0, []) == ("LOW", "APPROVED")
    assert fraud_rules.band_for(39, []) == ("LOW", "APPROVED")
    assert fraud_rules.band_for(40, []) == ("MEDIUM", "REVIEW")
    assert fraud_rules.band_for(69, []) == ("MEDIUM", "REVIEW")
    assert fraud_rules.band_for(70, []) == ("HIGH", "REJECTED")


def test_a_critical_signal_overrides_a_low_score() -> None:
    """Duplicate claims and face collisions must reject regardless of arithmetic
    - they are categorically disqualifying, not just risky."""
    critical = [_signal("SIMULTANEOUS_CLAIM", "critical", 40)]
    assert fraud_rules.band_for(5, critical) == ("HIGH", "REJECTED")


def test_low_match_margin_only_fires_inside_the_review_band() -> None:
    inside = {"steps": {"face": {"match_score": 0.35, "threshold": 0.42, "review_threshold": 0.30}}}
    above = {"steps": {"face": {"match_score": 0.80, "threshold": 0.42, "review_threshold": 0.30}}}
    missing = {"steps": {"face": {}}}
    assert len(fraud_rules._low_match_margin(inside)) == 1
    assert fraud_rules._low_match_margin(above) == []
    assert fraud_rules._low_match_margin(missing) == []


def test_software_key_raises_a_signal() -> None:
    soft = {"steps": {"fingerprint": {"security_level": "SOFTWARE", "method": "hmac"}}}
    tee = {"steps": {"fingerprint": {"security_level": "TEE"}}}
    assert fraud_rules._software_key_only(soft)[0].rule_id == "SOFTWARE_KEY_ONLY"
    assert fraud_rules._software_key_only(tee) == []


def test_menunggak_scales_with_arrears() -> None:
    assert fraud_rules._menunggak({"tunggakan_bulan": 0}) == []
    assert fraud_rules._menunggak({"tunggakan_bulan": 3})[0].weight == 15


def test_off_hours_skips_emergency_poli() -> None:
    """An IGD visit at 02:00 is a hospital working normally, not a fraud signal."""
    at_0200_wib = datetime(2026, 9, 8, 19, 0, tzinfo=UTC)  # 02:00 WIB next day
    assert fraud_rules._off_hours({"claim": {"poli": "Umum"}}, at_0200_wib)
    assert fraud_rules._off_hours({"claim": {"poli": "IGD"}}, at_0200_wib) == []


def test_face_collision_is_critical() -> None:
    hits = [{"peserta_id": "other", "score": 0.71}]
    signals = fraud_rules._face_collision(hits)
    assert signals[0].severity == "critical"
    assert fraud_rules.band_for(0, signals)[1] == "REJECTED"


# --------------------------------------------------------------------------- #
# Geo
# --------------------------------------------------------------------------- #
def test_haversine_jakarta_to_wamena() -> None:
    km = haversine_km([106.7996, -6.1789], [138.95, -4.0833])
    assert 3400 < km < 3700


def test_simultaneous_claims_imply_infinite_speed() -> None:
    """Two claims in the same minute at different cities: dividing by zero
    elapsed time must report the fraud, not crash."""
    assert implied_speed_kmh(500.0, 0.0) == float("inf")
    assert implied_speed_kmh(0.0, 0.0) == 0.0


def test_speed_calculation() -> None:
    assert implied_speed_kmh(120.0, 60.0) == pytest.approx(120.0)


# --------------------------------------------------------------------------- #
# Fingerprint attestation
# --------------------------------------------------------------------------- #
def _payload(**over) -> str:
    args = dict(session_id="s1", nonce="n1", device_uid="d1", no_bpjs="0001234567890",
                timestamp=1757000000)
    args.update(over)
    return attestation.canonical_payload(**args)


def test_canonical_payload_binds_every_field() -> None:
    base = _payload()
    assert base.startswith("identicare-v1|")
    for field in ("session_id", "nonce", "device_uid", "no_bpjs"):
        assert _payload(**{field: "CHANGED"}) != base, f"{field} is not bound into the signature"


def test_hmac_roundtrip() -> None:
    secret = b"k" * 32
    payload = _payload()
    sig = hmac.new(secret, payload.encode(), hashlib.sha256).digest()
    assert attestation.verify_hmac(payload=payload, signature=sig, shared_secret=secret).ok


def test_hmac_rejects_a_tampered_payload() -> None:
    """A signature captured for one session must not validate against another."""
    secret = b"k" * 32
    sig = hmac.new(secret, _payload().encode(), hashlib.sha256).digest()
    out = attestation.verify_hmac(
        payload=_payload(session_id="other"), signature=sig, shared_secret=secret
    )
    assert not out.ok and out.error_code == "SIGNATURE_INVALID"


def test_hmac_rejects_the_wrong_secret() -> None:
    payload = _payload()
    sig = hmac.new(b"k" * 32, payload.encode(), hashlib.sha256).digest()
    assert not attestation.verify_hmac(payload=payload, signature=sig, shared_secret=b"x" * 32).ok


def test_hmac_is_reported_as_software_not_tee() -> None:
    """Tier A has no hardware binding. Recording it as TEE would launder a shared
    secret into a hardware guarantee in the audit log."""
    secret = b"k" * 32
    sig = hmac.new(secret, _payload().encode(), hashlib.sha256).digest()
    assert attestation.verify_hmac(
        payload=_payload(), signature=sig, shared_secret=secret
    ).security_level == "SOFTWARE"


def test_ec_p256_roundtrip_and_rejection() -> None:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    der = key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    payload = _payload()
    sig = key.sign(payload.encode(), ec.ECDSA(hashes.SHA256()))

    good = attestation.verify_ec_p256(payload=payload, signature=sig, public_key_der=der)
    assert good.ok and good.security_level == "TEE"

    other = ec.generate_private_key(ec.SECP256R1())
    other_der = other.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    assert not attestation.verify_ec_p256(
        payload=payload, signature=sig, public_key_der=other_der
    ).ok


def test_unknown_method_is_not_supported() -> None:
    assert attestation.method_is_supported(attestation.METHOD_HMAC)
    assert attestation.method_is_supported(attestation.METHOD_KEYSTORE)
    assert not attestation.method_is_supported("trust_me_bro")


def test_parse_attestation_survives_garbage() -> None:
    out = attestation.parse_attestation(base64.b64decode("AAAA"))
    assert out["chain_verified"] is False
    assert "error" in out


# --------------------------------------------------------------------------- #
# Liveness scoring
# --------------------------------------------------------------------------- #
def _face(cx: float, nose_dx: float = 0.0, size: float = 200.0) -> Face:
    half = size / 2
    kps = np.array(
        [
            [cx - 40, 100.0],            # left eye
            [cx + 40, 100.0],            # right eye
            [cx + nose_dx, 140.0],       # nose
            [cx - 25, 180.0],            # left mouth
            [cx + 25, 180.0],            # right mouth
        ],
        dtype=np.float32,
    )
    bbox = np.array([cx - half, 50.0, cx + half, 50.0 + size], dtype=np.float32)
    return Face(bbox=bbox, kps=kps, det_score=0.95)


def test_yaw_proxy_is_zero_when_centred_and_signed_when_not() -> None:
    assert _face(200).yaw_proxy() == pytest.approx(0.0)
    assert _face(200, nose_dx=+20).yaw_proxy() > 0.2
    assert _face(200, nose_dx=-20).yaw_proxy() < -0.2


def test_yaw_proxy_is_scale_invariant() -> None:
    """Normalising by inter-ocular distance means moving nearer the camera must
    not read as turning."""
    small, big = _face(200, nose_dx=10), _face(200, nose_dx=10, size=400)
    assert small.yaw_proxy() == pytest.approx(big.yaw_proxy())


def test_motion_score_plateau() -> None:
    """A hand-held phone moves keypoints only a few pixels between frames. The
    earlier curve peaked at ~20 px and scored real captures at 0.15, which would
    have failed genuine users."""
    backend = liveness.ActiveChallengeV1()
    # The metric is mean |delta| over BOTH axes of all 5 keypoints, so a purely
    # horizontal shift of N px registers as N/2.
    assert backend._motion_score([_face(200), _face(200)]) == 0.0        # frozen -> photo
    assert 0.0 < backend._motion_score([_face(200), _face(202)]) < 1.0   # 1.0 mean, ramping
    assert backend._motion_score([_face(200), _face(208)]) == 1.0        # 4.0 mean, alive
    assert backend._motion_score([_face(200), _face(220)]) == 1.0        # 10.0 mean, alive
    assert backend._motion_score([_face(200), _face(400)]) == 0.0        # teleport -> cut


def test_challenge_scoring() -> None:
    backend = liveness.ActiveChallengeV1()
    turned = [_face(200), _face(200, nose_dx=25)]
    assert backend._challenge_score(turned, "turn_left") == pytest.approx(1.0)
    assert backend._challenge_score(turned, "turn_right") == 0.0
    assert backend._challenge_score([_face(200), _face(200)], "turn_left") == 0.0
    # No challenge issued -> neutral, never a free pass.
    assert backend._challenge_score(turned, None) == 0.5


def test_move_closer_uses_area_growth() -> None:
    backend = liveness.ActiveChallengeV1()
    closer = [_face(200, size=200), _face(200, size=300)]
    assert backend._challenge_score(closer, "move_closer") == pytest.approx(1.0)
    assert backend._challenge_score([_face(200), _face(200)], "move_closer") == 0.0


def test_a_single_frame_fails_closed() -> None:
    """One frame cannot demonstrate motion, so it must not be awarded the motion
    and challenge weights by default."""
    result = liveness.ActiveChallengeV1().evaluate([], [_face(200)], "turn_left", 0.7)
    assert not result.passed and result.score == 0.0


def test_challenge_text_covers_every_challenge() -> None:
    for challenge in liveness.CHALLENGES:
        assert liveness.CHALLENGE_TEXT[challenge]


def test_new_challenge_is_random() -> None:
    assert len({liveness.new_challenge() for _ in range(120)}) > 1


# --------------------------------------------------------------------------- #
# Session expiry
# --------------------------------------------------------------------------- #
def test_expiry_is_computed_from_expires_at() -> None:
    past = datetime.now(UTC) - timedelta(seconds=1)
    future = datetime.now(UTC) + timedelta(minutes=5)
    assert past < datetime.now(UTC) < future
