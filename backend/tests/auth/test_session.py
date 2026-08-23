"""The signed cookie. Every way verification can fail must answer None — a
bad cookie means "signed out", never a 500 during somebody's draft."""

import json

from draftkit.auth.session import (
    MAX_AGE_SECONDS,
    SessionUser,
    _b64,
    _sig,
    sign_session,
    verify_session,
)

SECRET = "test-secret"
USER = SessionUser(user_id="111", email="a@x.com", name="Ann", picture="p.png")


def forged(payload: bytes) -> str:
    """A token whose signature is genuine but whose payload we never produce —
    the shape a cookie from an older build of this app could take."""
    encoded = _b64(payload)
    return f"{encoded}.{_sig(SECRET, encoded)}"


def test_a_cookie_round_trips_every_field():
    assert verify_session(SECRET, sign_session(SECRET, USER)) == USER


def test_a_cookie_signed_with_another_secret_is_refused():
    assert verify_session("other-secret", sign_session(SECRET, USER)) is None


def test_a_payload_spliced_onto_another_users_signature_is_refused():
    payload, _ = sign_session(SECRET, USER, now=1000.0).split(".")
    _, signature = sign_session(SECRET, SessionUser("222", "b@x.com"), now=1000.0).split(".")
    assert verify_session(SECRET, f"{payload}.{signature}") is None


def test_a_cookie_expires_after_a_draft_season():
    token = sign_session(SECRET, USER, now=1000.0)
    assert verify_session(SECRET, token, now=1000.0 + 60) == USER
    assert verify_session(SECRET, token, now=1000.0 + MAX_AGE_SECONDS) is None


def test_wrong_segment_counts_are_refused():
    assert verify_session(SECRET, "onlyonesegment") is None
    assert verify_session(SECRET, "one.two.three") is None


def test_a_signed_but_undecodable_payload_is_refused():
    assert verify_session(SECRET, f"!!!.{_sig(SECRET, '!!!')}") is None


def test_a_signed_payload_that_is_not_json_is_refused():
    assert verify_session(SECRET, forged(b"not json at all")) is None


def test_a_signed_payload_that_is_not_a_claims_object_is_refused():
    assert verify_session(SECRET, forged(b"[1, 2, 3]")) is None


def test_a_payload_without_a_usable_expiry_is_refused():
    assert verify_session(SECRET, forged(json.dumps({"sub": "1"}).encode())) is None
    assert verify_session(SECRET, forged(json.dumps({"sub": "1", "exp": "never"}).encode())) is None


def test_a_payload_without_a_subject_is_refused():
    token = forged(json.dumps({"email": "a@x.com", "exp": 9_999_999_999}).encode())
    assert verify_session(SECRET, token) is None


def test_missing_optional_claims_default_to_empty_strings():
    claims = {"sub": "1", "email": "a@x.com", "exp": 9_999_999_999}
    user = verify_session(SECRET, forged(json.dumps(claims).encode()))
    assert user == SessionUser(user_id="1", email="a@x.com", name="", picture="")
