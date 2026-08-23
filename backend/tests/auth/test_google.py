"""The code exchange against Google, run entirely through a mock transport —
which is why the transport is injectable at all."""

import base64
import json

import httpx
import pytest

from draftkit.auth.google import (
    AUTHORIZE_URL,
    TOKEN_URL,
    ExchangeError,
    authorize_url,
    exchange_code,
)
from draftkit.auth.session import SessionUser


def token_of(claims: dict) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"header.{payload}.signature"


def run(status: int = 200, body: object = None, text: str | None = None) -> SessionUser:
    def handler(request: httpx.Request) -> httpx.Response:
        if text is not None:
            return httpx.Response(status, text=text)
        return httpx.Response(status, json=body)

    return exchange_code(
        "the-code",
        client_id="cid",
        client_secret="csec",
        redirect_uri="https://dk.test/auth/google/callback",
        transport=httpx.MockTransport(handler),
    )


def test_a_good_exchange_yields_the_identity_with_a_lowercased_email():
    claims = {"sub": "111", "email": "Ann@X.com", "name": "Ann", "picture": "p.png"}
    user = run(body={"id_token": token_of(claims)})
    assert user == SessionUser(user_id="111", email="ann@x.com", name="Ann", picture="p.png")


def test_the_exchange_posts_the_code_and_credentials_to_the_token_endpoint():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"id_token": token_of({"sub": "1", "email": "a@x.com"})})

    exchange_code(
        "the-code",
        client_id="cid",
        client_secret="csec",
        redirect_uri="https://r.test/cb",
        transport=httpx.MockTransport(handler),
    )
    assert seen["url"] == TOKEN_URL
    for fragment in ("code=the-code", "client_id=cid", "grant_type=authorization_code"):
        assert fragment in seen["body"]


def test_a_refused_exchange_names_the_status():
    with pytest.raises(ExchangeError, match="HTTP 400"):
        run(status=400, body={"error": "invalid_grant"})


def test_a_token_response_that_is_not_json_is_an_error():
    with pytest.raises(ExchangeError, match="not JSON"):
        run(text="<html>bad gateway</html>")


def test_a_token_response_without_an_id_token_is_an_error():
    with pytest.raises(ExchangeError, match="no id_token"):
        run(body={"access_token": "only"})


def test_a_token_response_that_is_not_an_object_is_an_error():
    with pytest.raises(ExchangeError, match="no id_token"):
        run(body=[1, 2, 3])


def test_an_id_token_that_is_not_a_jwt_is_an_error():
    with pytest.raises(ExchangeError, match="not a JWT"):
        run(body={"id_token": "only-two.segments"})


def test_an_id_token_payload_that_will_not_decode_is_an_error():
    with pytest.raises(ExchangeError, match="would not decode"):
        run(body={"id_token": "header.!!!.signature"})


def test_an_id_token_payload_that_is_not_a_claims_object_is_an_error():
    payload = base64.urlsafe_b64encode(b"[1, 2]").rstrip(b"=").decode()
    with pytest.raises(ExchangeError, match="claims object"):
        run(body={"id_token": f"header.{payload}.signature"})


@pytest.mark.parametrize("claims", [{"email": "a@x.com"}, {"sub": "111"}])
def test_an_identity_missing_its_subject_or_email_is_an_error(claims):
    with pytest.raises(ExchangeError, match="subject or email"):
        run(body={"id_token": token_of(claims)})


def test_missing_name_and_picture_default_to_empty():
    user = run(body={"id_token": token_of({"sub": "1", "email": "a@x.com"})})
    assert (user.name, user.picture) == ("", "")


def test_the_authorize_url_carries_everything_google_needs():
    url = authorize_url("cid", "https://dk.test/auth/google/callback", "st4te")
    assert url.startswith(AUTHORIZE_URL + "?")
    for fragment in (
        "client_id=cid",
        "redirect_uri=https%3A%2F%2Fdk.test%2Fauth%2Fgoogle%2Fcallback",
        "response_type=code",
        "scope=openid+email+profile",
        "state=st4te",
    ):
        assert fragment in url
