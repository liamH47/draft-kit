"""The board endpoint: pool minus drafted players, plus VORP, tags and advice."""

import pytest
from fastapi.testclient import TestClient

from draftkit.config import Settings
from draftkit.engine.recommend import TAG_POINTS
from draftkit.main import create_app
from draftkit.snapshots.store import SnapshotStore


@pytest.fixture
def client(tmp_path, fixture_fetcher):
    app = create_app(Settings(data_dir=tmp_path / "data"))
    app.state.snapshot_store = SnapshotStore(tmp_path / "data" / "snapshots", fixture_fetcher)
    return TestClient(app)


@pytest.fixture
def session(client):
    league = client.post(
        "/api/leagues", json={"num_teams": 12, "my_slot": 7, "scoring": "half_ppr"}
    ).json()
    board = client.post("/api/sessions", json={"league_id": league["id"]}).json()
    return {"league_id": league["id"], "session_id": board["session"]["id"]}


def board(client, session):
    resp = client.get(f"/api/sessions/{session['session_id']}/board")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_board_carries_pool_with_vorp_and_recommendations(client, session):
    data = board(client, session)
    assert len(data["available"]) >= 15
    first = data["available"][0]
    assert {"vorp", "vols", "adp", "adp_delta", "tier", "tag"} <= set(first)
    assert len(data["recommendations"]) == 5
    assert all(r["reasons"] for r in data["recommendations"])


def test_drafted_players_leave_the_board(client, session):
    sid = session["session_id"]
    before = board(client, session)
    target = before["available"][0]["player_id"]
    client.post(f"/api/sessions/{sid}/picks", json={"player_id": target})

    after = board(client, session)
    assert target not in {p["player_id"] for p in after["available"]}
    assert len(after["available"]) == len(before["available"]) - 1
    assert target not in {r["player_id"] for r in after["recommendations"]}


def test_my_picks_are_tracked_for_roster_need(client, session):
    sid = session["session_id"]
    rb = next(p for p in board(client, session)["available"] if p["position"] == "RB")
    client.post(f"/api/sessions/{sid}/picks", json={"player_id": rb["player_id"], "is_mine": True})

    data = board(client, session)
    assert data["my_counts"] == {"RB": 1}
    assert [p["player_id"] for p in data["my_players"]] == [rb["player_id"]]


def test_undo_puts_a_player_back_on_the_board(client, session):
    sid = session["session_id"]
    target = board(client, session)["available"][0]["player_id"]
    client.post(f"/api/sessions/{sid}/picks", json={"player_id": target})
    client.post(f"/api/sessions/{sid}/picks/undo")
    assert target in {p["player_id"] for p in board(client, session)["available"]}


def test_tags_reach_the_board_and_move_recommendations(client, session):
    lid = session["league_id"]
    data = board(client, session)
    # Tag the runner-up recommendation: the tag must reach his board row, his
    # recommendation reasons, and lift him over the old #1. (Whether a tag can
    # promote an arbitrary outsider is engine maths, unit-tested — an API test
    # that depended on the exact score gaps broke every time the model moved.)
    runner_up = data["recommendations"][1]
    target = runner_up["player_id"]
    client.put(f"/api/leagues/{lid}/tags/{target}", json={"tag": "target"})

    tagged = board(client, session)
    row = next(p for p in tagged["available"] if p["player_id"] == target)
    assert row["tag"] == "target"
    promoted = next(r for r in tagged["recommendations"] if r["player_id"] == target)
    assert "you tagged him a target" in promoted["reasons"]
    assert promoted["score"] == pytest.approx(runner_up["score"] + TAG_POINTS["target"])


def test_fade_tag_removes_a_player_from_the_top_recommendations(client, session):
    lid = session["league_id"]
    top = board(client, session)["recommendations"][0]["player_id"]
    client.put(f"/api/leagues/{lid}/tags/{top}", json={"tag": "fade"})
    after = board(client, session)
    assert after["recommendations"][0]["player_id"] != top


def test_scoring_format_changes_the_board_ordering(tmp_path, fixture_fetcher):
    def make(scoring):
        app = create_app(Settings(data_dir=tmp_path / scoring))
        app.state.snapshot_store = SnapshotStore(tmp_path / "snapshots", fixture_fetcher)
        c = TestClient(app)
        league = c.post("/api/leagues", json={"num_teams": 12, "scoring": scoring}).json()
        sid = c.post("/api/sessions", json={"league_id": league["id"]}).json()["session"]["id"]
        return c.get(f"/api/sessions/{sid}/board").json()

    ppr = make("ppr")
    standard = make("standard")
    # Pass-catchers gain in PPR; the same player must score higher there.
    name = "Christian McCaffrey"
    ppr_pts = next(p for p in ppr["available"] if p["name"] == name)["points"]
    std_pts = next(p for p in standard["available"] if p["name"] == name)["points"]
    assert ppr_pts > std_pts


def test_tier_urgency_still_fires_on_my_own_pick(client, session):
    """picks_until_my_turn is 0 on the clock, which must not silence tier
    urgency at the only moment advice matters — it keys off the gap to my NEXT
    turn instead. The payload keeps the raw 0: the UI reads it as 'your pick'."""
    sid = session["session_id"]
    data = board(client, session)
    for player in data["available"][:6]:  # slots 1-6 pick; I'm slot 7, now up
        client.post(f"/api/sessions/{sid}/picks", json={"player_id": player["player_id"]})

    mine = board(client, session)
    assert mine["picks_until_my_turn"] == 0
    assert any(
        "until your turn" in reason for rec in mine["recommendations"] for reason in rec["reasons"]
    )


def test_board_reports_source_freshness(client, session):
    data = board(client, session)
    assert "sleeper_players" in data["sources"]
    assert data["sources"]["sleeper_players"]["stale"] is False


def test_board_survives_a_dead_network(tmp_path, fixture_fetcher, failing_fetcher):
    settings = Settings(data_dir=tmp_path / "data")
    warm = create_app(settings)
    warm.state.snapshot_store = SnapshotStore(tmp_path / "data" / "snapshots", fixture_fetcher)
    c = TestClient(warm)
    league = c.post("/api/leagues", json={"num_teams": 12}).json()
    sid = c.post("/api/sessions", json={"league_id": league["id"]}).json()["session"]["id"]
    c.get(f"/api/sessions/{sid}/board")  # warms the snapshots

    offline = create_app(settings)
    offline.state.snapshot_store = SnapshotStore(tmp_path / "data" / "snapshots", failing_fetcher)
    data = TestClient(offline).get(f"/api/sessions/{sid}/board").json()
    assert len(data["available"]) >= 15  # the draft goes on
