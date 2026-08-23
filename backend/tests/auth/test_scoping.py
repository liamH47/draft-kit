"""Two signed-in users must be invisible to each other. Every assertion here
was an open IDOR before user_id was threaded through the API — the tables
were scoped from day one, but nothing passed a user in."""

import pytest
from fastapi.testclient import TestClient

from draftkit.auth.session import COOKIE_NAME, SessionUser, sign_session
from draftkit.config import Settings
from draftkit.db import repo
from draftkit.main import create_app
from draftkit.snapshots.store import SnapshotStore

SECRET = "test-secret"


def make_app(tmp_path, fixture_fetcher, **overrides):
    config: dict = {
        "data_dir": tmp_path / "data",
        "auth": "google",
        "google_client_id": "cid",
        "google_client_secret": "csec",
        "secret_key": SECRET,
        "allowed_emails": ["ann@x.com", "bob@x.com"],
        "owner_email": "ann@x.com",
        "public_url": "https://dk.test",
    }
    app = create_app(Settings(**{**config, **overrides}))
    app.state.snapshot_store = SnapshotStore(tmp_path / "data" / "snapshots", fixture_fetcher)
    return app


def client_for(app, sub: str, email: str) -> TestClient:
    client = TestClient(app, base_url="https://testserver")
    client.cookies.set(COOKIE_NAME, sign_session(SECRET, SessionUser(sub, email)))
    return client


@pytest.fixture
def pair(tmp_path, fixture_fetcher):
    app = make_app(tmp_path, fixture_fetcher)
    return client_for(app, "111", "ann@x.com"), client_for(app, "222", "bob@x.com")


def test_leagues_and_sessions_are_invisible_across_users(pair):
    ann, bob = pair
    league = ann.post("/api/leagues", json={}).json()
    sid = ann.post("/api/sessions", json={"league_id": league["id"]}).json()["session"]["id"]

    assert bob.get("/api/leagues").json() == []
    assert bob.get(f"/api/leagues/{league['id']}").status_code == 404
    assert bob.get("/api/sessions").json() == []
    assert bob.get(f"/api/sessions/{sid}").status_code == 404
    assert bob.get(f"/api/sessions/{sid}/board").status_code == 404
    assert bob.get(f"/api/sessions/{sid}/events").status_code == 404
    assert bob.post(f"/api/sessions/{sid}/picks", json={"player_id": "4034"}).status_code == 404
    assert bob.put(f"/api/sessions/{sid}/picks/1", json={"player_id": "4034"}).status_code == 404
    assert bob.post(f"/api/sessions/{sid}/picks/undo").status_code == 404
    # Nor can Bob hang his own session on Ann's league.
    assert bob.post("/api/sessions", json={"league_id": league["id"]}).status_code == 404

    # Ann still sees everything, and her board still builds.
    assert [lg["id"] for lg in ann.get("/api/leagues").json()] == [league["id"]]
    assert ann.get(f"/api/sessions/{sid}/board").status_code == 200


def test_a_pick_lands_on_the_owners_board(pair):
    ann, _ = pair
    league = ann.post("/api/leagues", json={}).json()
    sid = ann.post("/api/sessions", json={"league_id": league["id"]}).json()["session"]["id"]
    resp = ann.post(f"/api/sessions/{sid}/picks", json={"player_id": "4034"})
    assert resp.status_code == 200
    assert resp.json()["picks_made"] == 1


def test_tags_are_private_and_so_are_their_mirror_files(pair, tmp_path):
    ann, bob = pair
    ann.put("/api/tags/4034", json={"tag": "target"})
    assert "4034" in ann.get("/api/tags").json()
    assert bob.get("/api/tags").json() == {}

    # Ann's mirror lands in her own directory, and restore reads only it.
    assert (tmp_path / "data" / "users" / "111" / "tags.json").is_file()
    assert ann.post("/api/tags/restore").json()["restored"] == 1
    # Bob has no file of his own, so restore cannot hand him Ann's opinions.
    assert bob.post("/api/tags/restore").status_code == 404


def test_ranking_lists_are_private_and_so_is_their_column(pair, tmp_path):
    ann, bob = pair
    body = ann.put("/api/rankings/my-guys", json={"text": "1. Christian McCaffrey RB SF"}).json()
    assert body["matched"] == 1

    assert bob.get("/api/rankings").json()["lists"] == []
    assert bob.get("/api/rankings/my-guys").status_code == 404
    assert bob.delete("/api/rankings/my-guys").status_code == 404
    assert bob.post("/api/rankings/restore").status_code == 404
    assert (tmp_path / "data" / "users" / "111" / "rankings.json").is_file()

    ann_cmc = {p["name"]: p for p in ann.get("/api/players").json()["players"]}
    bob_cmc = {p["name"]: p for p in bob.get("/api/players").json()["players"]}
    assert "custom:my-guys" in ann_cmc["Christian McCaffrey"]["rank_by_source"]
    assert "custom:my-guys" not in bob_cmc["Christian McCaffrey"]["rank_by_source"]


def test_espn_import_is_the_owners_alone(pair):
    ann, bob = pair
    refused = bob.post("/api/leagues/import/espn", json={"espn_league_id": "1234567"})
    assert refused.status_code == 403
    assert "site owner" in refused.json()["detail"]

    allowed = ann.post("/api/leagues/import/espn", json={"espn_league_id": "1234567"})
    assert allowed.status_code == 200
    assert allowed.json()["platform"] == "espn"


def test_with_no_owner_configured_nobody_imports_from_espn(tmp_path, fixture_fetcher):
    """The fail-safe default: an operator who never set DRAFTKIT_OWNER_EMAIL
    has opted nobody in, themselves included."""
    app = make_app(tmp_path, fixture_fetcher, owner_email=None)
    ann = client_for(app, "111", "ann@x.com")
    resp = ann.post("/api/leagues/import/espn", json={"espn_league_id": "1234567"})
    assert resp.status_code == 403


def test_snapshot_warming_sees_every_users_league_shapes(tmp_path, fixture_fetcher):
    """league_team_counts crosses users ON PURPOSE: warming fetches one FFC
    snapshot per team count, and a warm run that skipped a friend's 8-team
    league would leave their offline draft unreadable."""
    app = make_app(tmp_path, fixture_fetcher)
    client_for(app, "111", "ann@x.com").post("/api/leagues", json={"num_teams": 8})
    client_for(app, "222", "bob@x.com").post("/api/leagues", json={"num_teams": 14})
    assert repo.league_team_counts(app.state.db) == {8, 14}
