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
    data = board(client, session)
    # Tag the runner-up recommendation: the tag must reach his board row, his
    # recommendation reasons, and lift him over the old #1. (Whether a tag can
    # promote an arbitrary outsider is engine maths, unit-tested — an API test
    # that depended on the exact score gaps broke every time the model moved.)
    runner_up = data["recommendations"][1]
    target = runner_up["player_id"]
    client.put(f"/api/tags/{target}", json={"tag": "target"})

    tagged = board(client, session)
    row = next(p for p in tagged["available"] if p["player_id"] == target)
    assert row["tag"] == "target"
    promoted = next(r for r in tagged["recommendations"] if r["player_id"] == target)
    assert "you tagged him a target" in promoted["reasons"]
    assert promoted["score"] == pytest.approx(runner_up["score"] + TAG_POINTS["target"])


def test_fade_tag_removes_a_player_from_the_top_recommendations(client, session):
    top = board(client, session)["recommendations"][0]["player_id"]
    client.put(f"/api/tags/{top}", json={"tag": "fade"})
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


def test_scarcity_is_priced_on_my_own_pick(client, session):
    """picks_until_my_turn is 0 on the clock, which must not silence scarcity
    at the only moment advice matters — what waiting costs is measured to my
    NEXT pick. The payload keeps the raw 0: the UI reads it as 'your pick'."""
    sid = session["session_id"]
    data = board(client, session)
    for player in data["available"][:6]:  # slots 1-6 pick; I'm slot 7, now up
        client.post(f"/api/sessions/{sid}/picks", json={"player_id": player["player_id"]})

    mine = board(client, session)
    assert mine["picks_until_my_turn"] == 0
    assert all(r["vona"] is not None for r in mine["recommendations"])
    assert any(p["vona"] is not None for p in mine["available"])


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


def test_a_player_who_lasted_past_his_adp_reads_as_a_bargain(client, session):
    """The column header promises "+ is a steal", and the score's own ADP term
    agrees. This read the other way round, so the best value on the board was
    painted red as a reach."""
    sid = session["session_id"]
    for player in board(client, session)["available"][:12]:
        client.post(f"/api/sessions/{sid}/picks", json={"player_id": player["player_id"]})

    data = board(client, session)
    on_clock = data["on_the_clock"]["overall_no"]
    priced = [p for p in data["available"] if p["adp"] is not None]
    assert priced
    for player in priced:
        assert player["adp_delta"] == pytest.approx(on_clock - player["adp"], abs=0.05)
    # The sign reads the way the column header promises it does.
    cheapest = min(priced, key=lambda p: p["adp"])
    assert (cheapest["adp_delta"] > 0) is (cheapest["adp"] < on_clock)


def test_the_board_ships_one_tier_and_it_is_the_experts(client, session):
    """The row's tier is the one the reader should trust: Boris Chen's where
    he covers the position, the projection-gap tier only where he doesn't.
    Shipping both confused everyone — gap tiers at the top of a steep curve
    degenerate to one man per tier ("RB5, tier 5")."""
    pool = {p["player_id"]: p for p in client.get("/api/players").json()["players"]}
    rows = board(client, session)["available"]
    expert_positions = {p["position"] for p in pool.values() if p["tier_expert"]}
    assert expert_positions  # the fixture does carry Boris Chen tiers
    for row in rows:
        assert "tier_expert" not in row
        raw = pool[row["player_id"]]
        expected = raw["tier_expert"] if row["position"] in expert_positions else raw["tier"]
        assert row["tier"] == expected


def test_the_board_names_the_pick_the_wait_cost_is_measured_against(client, session):
    """Slot 7 of 12: on the clock at 7, back on at 18. The card says
    "waiting to pick N costs..." and N must be this number, not a guess."""
    data = board(client, session)
    assert data["my_next_pick"] == 18
    assert all("value" in r and "vorp" not in r for r in data["recommendations"])
