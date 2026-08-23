"""The sign-in flow end to end, with the code exchange stubbed at the seam
main.py provides for it — the same pattern as the snapshot store."""

import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from draftkit.auth.google import ExchangeError
from draftkit.auth.session import COOKIE_NAME, MAX_AGE_SECONDS, SessionUser, sign_session
from draftkit.config import Settings
from draftkit.db import repo
from draftkit.main import create_app

SECRET = "test-secret"
GOOGLE: dict[str, Any] = {
    "auth": "google",
    "google_client_id": "cid",
    "google_client_secret": "csec",
    "secret_key": SECRET,
    "allowed_emails": ["ann@x.com", "bob@x.com"],
    "owner_email": "ann@x.com",
    "public_url": "https://dk.test",
}
ANN = SessionUser(user_id="111", email="ann@x.com", name="Ann", picture="a.png")


def google_app(tmp_path, **overrides):
    app = create_app(Settings(data_dir=tmp_path / "data", **{**GOOGLE, **overrides}))
    app.state.token_exchanger = lambda code: ANN
    return app


def signed_in(client: TestClient, user: SessionUser = ANN, *, now: float | None = None) -> None:
    client.cookies.set(COOKIE_NAME, sign_session(SECRET, user, now=now))


def start_login(client: TestClient) -> str:
    """Walk the login redirect and hand back the state Google would echo."""
    resp = client.get("/auth/google/login", follow_redirects=False)
    assert resp.status_code == 307
    return parse_qs(urlparse(resp.headers["location"]).query)["state"][0]


# --- the login redirect ------------------------------------------------------


def test_login_sends_the_browser_to_google_with_a_state_it_also_keeps(tmp_path):
    client = TestClient(google_app(tmp_path), base_url="https://testserver")
    resp = client.get("/auth/google/login", follow_redirects=False)
    location = resp.headers["location"]
    assert location.startswith("https://accounts.google.com/")
    state = parse_qs(urlparse(location).query)["state"][0]
    assert client.cookies.get("dk_oauth_state") == state


def test_the_whole_flow_is_absent_when_auth_is_off(tmp_path):
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    assert client.get("/auth/google/login", follow_redirects=False).status_code == 404
    assert client.get("/auth/google/callback", follow_redirects=False).status_code == 404


# --- the callback ------------------------------------------------------------


def test_a_good_callback_sets_the_session_cookie_and_records_the_user(tmp_path):
    app = google_app(tmp_path)
    client = TestClient(app, base_url="https://testserver")
    state = start_login(client)
    resp = client.get(f"/auth/google/callback?code=c&state={state}", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/"
    assert client.cookies.get(COOKIE_NAME) is not None
    assert client.get("/api/me").json()["user"]["email"] == "ann@x.com"
    row = app.state.db.execute("SELECT * FROM user_account").fetchone()
    assert (row["google_sub"], row["email"]) == ("111", "ann@x.com")


def test_a_state_that_does_not_match_the_cookie_is_refused(tmp_path):
    client = TestClient(google_app(tmp_path), base_url="https://testserver")
    start_login(client)
    resp = client.get("/auth/google/callback?code=c&state=wrong", follow_redirects=False)
    assert resp.status_code == 400
    assert "state mismatch" in resp.json()["detail"]


def test_a_callback_with_no_state_cookie_at_all_is_refused(tmp_path):
    client = TestClient(google_app(tmp_path), base_url="https://testserver")
    resp = client.get("/auth/google/callback?code=c&state=s", follow_redirects=False)
    assert resp.status_code == 400


def test_a_callback_without_a_code_is_refused(tmp_path):
    client = TestClient(google_app(tmp_path), base_url="https://testserver")
    state = start_login(client)
    resp = client.get(f"/auth/google/callback?state={state}", follow_redirects=False)
    assert resp.status_code == 400
    assert "no authorization code" in resp.json()["detail"]


def test_a_failed_exchange_is_a_visible_502_not_a_blank_page(tmp_path):
    app = google_app(tmp_path)

    def explode(code):
        raise ExchangeError("Google refused the code exchange (HTTP 400)")

    app.state.token_exchanger = explode
    client = TestClient(app, base_url="https://testserver")
    state = start_login(client)
    resp = client.get(f"/auth/google/callback?code=c&state={state}", follow_redirects=False)
    assert resp.status_code == 502
    assert "Google sign-in failed" in resp.json()["detail"]


def test_an_email_google_verified_but_nobody_invited_is_turned_away(tmp_path):
    app = google_app(tmp_path)
    app.state.token_exchanger = lambda code: SessionUser("999", "stranger@x.com")
    client = TestClient(app, base_url="https://testserver")
    state = start_login(client)
    resp = client.get(f"/auth/google/callback?code=c&state={state}", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login?error=denied"
    assert client.cookies.get(COOKIE_NAME) is None
    assert app.state.db.execute("SELECT COUNT(*) AS n FROM user_account").fetchone()["n"] == 0


def test_signing_in_again_bumps_last_login_and_keeps_first_login(tmp_path):
    app = google_app(tmp_path)
    first = repo.upsert_user(
        app.state.db, google_sub="111", email="ann@x.com", name="Ann", picture="a.png"
    )
    time.sleep(0.01)
    second = repo.upsert_user(
        app.state.db, google_sub="111", email="ann@x.com", name="Ann Renamed", picture="b.png"
    )
    assert second["first_login"] == first["first_login"]
    assert second["last_login"] > first["last_login"]
    assert second["name"] == "Ann Renamed"
    assert app.state.db.execute("SELECT COUNT(*) AS n FROM user_account").fetchone()["n"] == 1


# --- /api/me and logout ------------------------------------------------------


def test_me_reports_the_local_user_when_auth_is_off(tmp_path):
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    body = client.get("/api/me").json()
    assert body["auth"] == "off"
    assert body["user"]["user_id"] == "local"


def test_me_is_a_200_with_a_null_user_rather_than_a_401(tmp_path):
    """A 401 here plus the client's 401-goes-to-login rule would loop on the
    login page itself."""
    client = TestClient(google_app(tmp_path), base_url="https://testserver")
    assert client.get("/api/me").json() == {"auth": "google", "user": None}
    client.cookies.set(COOKIE_NAME, "garbage")
    assert client.get("/api/me").json()["user"] is None


def test_me_names_the_signed_in_user(tmp_path):
    client = TestClient(google_app(tmp_path), base_url="https://testserver")
    signed_in(client)
    assert client.get("/api/me").json()["user"]["name"] == "Ann"


def test_logout_clears_the_cookie_even_with_auth_off(tmp_path):
    client = TestClient(google_app(tmp_path), base_url="https://testserver")
    state = start_login(client)
    client.get(f"/auth/google/callback?code=c&state={state}", follow_redirects=False)
    assert client.get("/api/me").json()["user"] is not None
    assert client.post("/auth/logout").json() == {"ok": True}
    assert client.get("/api/me").json()["user"] is None
    off = TestClient(create_app(Settings(data_dir=tmp_path / "data2")))
    assert off.post("/auth/logout").json() == {"ok": True}


# --- what the cookie gates ---------------------------------------------------


@pytest.mark.parametrize("cookie", [None, "garbage", "expired"])
def test_data_routes_answer_401_without_a_live_cookie(tmp_path, cookie):
    client = TestClient(google_app(tmp_path), base_url="https://testserver")
    if cookie == "expired":
        signed_in(client, now=time.time() - MAX_AGE_SECONDS - 60)
    elif cookie:
        client.cookies.set(COOKIE_NAME, cookie)
    resp = client.get("/api/leagues")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "not signed in"


def test_a_live_cookie_opens_the_data_routes(tmp_path):
    client = TestClient(google_app(tmp_path), base_url="https://testserver")
    signed_in(client)
    assert client.get("/api/leagues").json() == []


def test_health_stays_open_for_uptime_probes(tmp_path):
    client = TestClient(google_app(tmp_path), base_url="https://testserver")
    assert client.get("/api/health").status_code == 200
