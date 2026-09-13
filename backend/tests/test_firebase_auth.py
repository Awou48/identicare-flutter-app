from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import get_settings
from app.security import firebase_auth as fa
from app.utils.errors import ApiError

PROJECT = "identicare-591e3"
KID = "test-key-1"


@pytest.fixture
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def settings():
    return get_settings()


@pytest.fixture(autouse=True)
def public_key_mode(signing_key, monkeypatch):
    """Force the public-key path and serve our own key for KID."""
    fa.reset_for_tests()
    monkeypatch.setattr(fa, "_initialised", True)
    monkeypatch.setattr(fa, "_admin_available", False)
    monkeypatch.setattr(fa, "_public_key_available", True)
    monkeypatch.setattr(fa, "_fetch_certs", lambda: {KID: signing_key.public_key()})
    yield
    fa.reset_for_tests()


def make_token(signing_key, **overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": f"https://securetoken.google.com/{PROJECT}",
        "aud": PROJECT,
        "sub": "firebase-uid-abc123",
        "auth_time": now - 60,
        "iat": now - 60,
        "exp": now + 3600,
        "email": "marcel@example.com",
    }
    claims.update(overrides)
    return jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": KID})


def test_genuine_token_is_accepted(signing_key, settings):
    """The case that was failing in production: a real app token, no service account on disk, must verify."""
    user = fa.verify(make_token(signing_key), settings)
    assert user.uid == "firebase-uid-abc123"
    assert user.email == "marcel@example.com"
    assert user.method == "google-public-keys"
    assert user.dev_mode is False


def test_status_reports_the_live_path():
    assert fa.status() == "google-public-keys"
    assert fa.is_available() is True


def test_token_for_another_project_is_rejected(signing_key, settings):
    """A token minted for a different Firebase project is a valid Google signature - only the audience check
    stops it being accepted here.
    """
    with pytest.raises(ApiError) as exc:
        fa.verify(make_token(signing_key, aud="some-other-project"), settings)
    assert exc.value.status_code == 401
    assert "project" in exc.value.message.lower()


def test_wrong_issuer_is_rejected(signing_key, settings):
    with pytest.raises(ApiError):
        fa.verify(make_token(signing_key, iss="https://evil.example.com"), settings)


def test_expired_token_is_rejected(signing_key, settings):
    now = int(time.time())
    with pytest.raises(ApiError) as exc:
        fa.verify(
            make_token(signing_key, exp=now - fa.LEEWAY_SECONDS - 60, iat=now - 7200),
            settings,
        )
    assert "berakhir" in exc.value.message.lower()


def test_leeway_tolerates_small_clock_skew(signing_key, settings):
    """Deliberate: a token a few seconds past expiry still verifies, because the phone's clock and Google's
    are never exactly aligned and a hard cutoff makes users randomly fail mid-session. The window is
    LEEWAY_SECONDS, not unbounded.
    """
    now = int(time.time())
    user = fa.verify(make_token(signing_key, exp=now - 5), settings)
    assert user.uid == "firebase-uid-abc123"


def test_token_signed_by_a_different_key_is_rejected(settings):
    """The forgery that matters: correct claims, wrong signer."""
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(ApiError):
        fa.verify(make_token(attacker), settings)


def test_alg_none_is_rejected(signing_key, settings):
    """Classic JWT attack - strip the signature and set alg to none."""
    forged = jwt.encode({"sub": "x", "aud": PROJECT}, key="", algorithm="none")
    with pytest.raises(ApiError):
        fa.verify(forged, settings)


def test_missing_subject_is_rejected(signing_key, settings):
    with pytest.raises(ApiError):
        fa.verify(make_token(signing_key, sub=""), settings)


def test_unknown_kid_is_rejected(signing_key, settings):
    token = jwt.encode(
        {
            "iss": f"https://securetoken.google.com/{PROJECT}",
            "aud": PROJECT,
            "sub": "u",
            "iat": int(time.time()),
            "exp": int(time.time()) + 600,
        },
        signing_key,
        algorithm="RS256",
        headers={"kid": "a-kid-google-never-issued"},
    )
    with pytest.raises(ApiError):
        fa.verify(token, settings)


def test_empty_token_is_rejected(settings):
    with pytest.raises(ApiError):
        fa.verify("", settings)


def test_future_auth_time_is_rejected(signing_key, settings):
    with pytest.raises(ApiError):
        fa.verify(make_token(signing_key, auth_time=int(time.time()) + 9999), settings)


def test_dev_bypass_is_unreachable_when_public_keys_work(settings):
    """dev:<uid> must not be a back door once real verification is available."""
    with pytest.raises(ApiError):
        fa.verify("dev:anyone", settings)
