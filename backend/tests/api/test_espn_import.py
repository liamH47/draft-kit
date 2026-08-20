"""Importing a league's real settings instead of asking the user to retype them.

Roster shape sets replacement level, so a transcription slip here silently
mis-prices every player at that position for the whole draft. Reading it from
the league removes the error class rather than validating it.
"""

import pytest
from fastapi.testclient import TestClient

from draftkit.config import Settings
from draftkit.main import create_app
from draftkit.snapshots.store import SnapshotStore
from draftkit.sources.base import RequestSpec


@pytest.fixture
def client(tmp_path, fixture_fetcher):
    app = create_app(Settings(data_dir=tmp_path / "data"))
    app.state.snapshot_store = SnapshotStore(tmp_path / "data" / "snapshots", fixture_fetcher)
    return TestClient(app)


def test_import_reads_the_real_roster_and_scoring(client):
    league = client.post(
        "/api/leagues/import/espn", json={"espn_league_id": "1234567", "my_slot": 7}
    ).json()

    assert league["name"] == "The Home League"
    assert league["platform"] == "espn"
    assert league["num_teams"] == 12
    assert league["my_slot"] == 7
    # The two settings a wizard would most easily get wrong:
    assert league["config"]["roster"]["wr"] == 3
    assert league["config"]["roster"]["flex"] == 2
    # Half-PPR derived from the league's own reception value, not guessed.
    assert league["scoring_preset"] == "half_ppr"
    assert league["config"]["scoring"]["weights"]["rec"] == 0.5
    # 11 starters + 6 bench.
    assert league["rounds"] == 17


def test_imported_roster_moves_replacement_level(client):
    """The whole point: a 3-WR league must value receivers differently."""
    from draftkit.engine.baselines import starters_by_position
    from draftkit.models.league import LeagueConfig

    imported = client.post("/api/leagues/import/espn", json={"espn_league_id": "1234567"}).json()
    config = LeagueConfig(**imported["config"])
    default = LeagueConfig(**{**imported["config"], "roster": {}})

    assert starters_by_position(config.roster)["WR"] > starters_by_position(default.roster)["WR"]


def test_import_rejects_a_slot_beyond_the_league_size(client):
    resp = client.post(
        "/api/leagues/import/espn", json={"espn_league_id": "1234567", "my_slot": 99}
    )
    assert resp.status_code == 422
    assert "12 teams" in resp.json()["detail"]


def test_a_custom_name_and_autodraft_count_survive_the_import(client):
    league = client.post(
        "/api/leagues/import/espn",
        json={"espn_league_id": "1234567", "name": "My nickname", "autodraft_count": 4},
    ).json()
    assert league["name"] == "My nickname"
    assert league["config"]["autodraft_count"] == 4


def test_an_unreachable_league_explains_the_cookies(tmp_path, failing_fetcher):
    app = create_app(Settings(data_dir=tmp_path / "data"))
    app.state.snapshot_store = SnapshotStore(tmp_path / "data" / "snapshots", failing_fetcher)
    resp = TestClient(app).post("/api/leagues/import/espn", json={"espn_league_id": "999"})
    assert resp.status_code == 502
    assert "private" in resp.json()["detail"]


def test_credentials_come_from_the_environment_not_the_caller(tmp_path, monkeypatch):
    """Cookies must never travel in a request body, where they would end up in
    logs and browser history."""
    seen: list[RequestSpec] = []

    def spy(spec):
        seen.append(spec)
        raise ConnectionError("stop here")

    settings = Settings(data_dir=tmp_path / "data", espn_s2="SECRET_S2", espn_swid="{SECRET-SWID}")
    app = create_app(settings)
    app.state.snapshot_store = SnapshotStore(tmp_path / "data" / "snapshots", spy)
    resp = TestClient(app).post(
        "/api/leagues/import/espn",
        json={"espn_league_id": "1234567", "espn_s2": "FROM_BODY"},
    )
    assert resp.status_code == 502
    cookie = seen[0].headers["Cookie"]
    assert "SECRET_S2" in cookie  # taken from settings
    assert "FROM_BODY" not in cookie  # never from the request body
    assert "SECRET_S2" not in resp.text  # and never echoed back


def test_public_leagues_send_no_cookie_header(tmp_path):
    seen: list[RequestSpec] = []

    def spy(spec):
        seen.append(spec)
        raise ConnectionError("stop here")

    app = create_app(Settings(data_dir=tmp_path / "data"))
    app.state.snapshot_store = SnapshotStore(tmp_path / "data" / "snapshots", spy)
    TestClient(app).post("/api/leagues/import/espn", json={"espn_league_id": "1"})
    assert "Cookie" not in seen[0].headers
