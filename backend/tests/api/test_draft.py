"""Draft core: league setup, pick entry, undo, tags, and crash-safe resume."""

import pytest
from fastapi.testclient import TestClient

from draftkit.config import Settings
from draftkit.main import create_app


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(Settings(data_dir=tmp_path / "data")))


def make_league(client, **overrides):
    body = {"name": "Home league", "num_teams": 12, "my_slot": 7, "rounds": 15} | overrides
    resp = client.post("/api/leagues", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def make_session(client, league_id):
    resp = client.post("/api/sessions", json={"league_id": league_id, "name": "Mock"})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_league_roundtrip_persists_scoring(client):
    league = make_league(client, scoring="ppr", scoring_overrides={"pass_td": 6.0})
    assert league["scoring_preset"] == "ppr"
    assert league["config"]["scoring"]["weights"]["rec"] == 1.0
    assert league["config"]["scoring"]["weights"]["pass_td"] == 6.0
    assert client.get(f"/api/leagues/{league['id']}").json() == league
    assert len(client.get("/api/leagues").json()) == 1


def test_league_rejects_slot_beyond_team_count(client):
    resp = client.post("/api/leagues", json={"num_teams": 10, "my_slot": 11})
    assert resp.status_code == 422


def test_new_session_starts_empty_with_correct_clock(client):
    league = make_league(client)
    board = make_session(client, league["id"])
    assert board["picks_made"] == 0
    assert board["total_picks"] == 180
    assert board["on_the_clock"] == {"overall_no": 1, "round_no": 1, "slot": 1}
    assert board["picks_until_my_turn"] == 6  # slot 7


def test_picks_advance_the_snake_and_flag_mine(client):
    league = make_league(client)
    session = make_session(client, league["id"])["session"]
    sid = session["id"]

    board = {}
    for i in range(6):
        board = client.post(f"/api/sessions/{sid}/picks", json={"player_id": f"p{i}"}).json()
    assert board["picks_until_my_turn"] == 0  # I'm on the clock at pick 7

    mine = client.post(f"/api/sessions/{sid}/picks", json={"player_id": "mine"}).json()
    assert mine["pick"]["overall_no"] == 7
    assert mine["pick"]["is_mine"] is True
    assert mine["my_player_ids"] == ["mine"]
    # Next turn is overall 18 (round 2 reverses); 10 picks in between.
    assert mine["picks_until_my_turn"] == 10

    # Round 2 reverses direction: pick 13 belongs to slot 12.
    for i in range(5):
        client.post(f"/api/sessions/{sid}/picks", json={"player_id": f"q{i}"})
    board = client.post(f"/api/sessions/{sid}/picks", json={"player_id": "r13"}).json()
    assert board["pick"]["overall_no"] == 13
    assert (board["pick"]["round_no"], board["pick"]["slot"]) == (2, 12)


def test_duplicate_player_rejected(client):
    league = make_league(client)
    sid = make_session(client, league["id"])["session"]["id"]
    client.post(f"/api/sessions/{sid}/picks", json={"player_id": "dup"})
    resp = client.post(f"/api/sessions/{sid}/picks", json={"player_id": "dup"})
    assert resp.status_code == 409


def test_undo_frees_the_player_and_rewinds_the_clock(client):
    league = make_league(client)
    sid = make_session(client, league["id"])["session"]["id"]
    client.post(f"/api/sessions/{sid}/picks", json={"player_id": "a"})
    client.post(f"/api/sessions/{sid}/picks", json={"player_id": "b"})

    board = client.post(f"/api/sessions/{sid}/picks/undo").json()
    assert board["undone"]["player_id"] == "b"
    assert board["picks_made"] == 1
    assert board["drafted_player_ids"] == ["a"]
    # The undone player can be drafted again, and reuses the freed pick slot.
    again = client.post(f"/api/sessions/{sid}/picks", json={"player_id": "b"})
    assert again.status_code == 200
    assert again.json()["pick"]["overall_no"] == 2


def test_undo_on_empty_board_is_a_noop(client):
    league = make_league(client)
    sid = make_session(client, league["id"])["session"]["id"]
    board = client.post(f"/api/sessions/{sid}/picks/undo").json()
    assert board["undone"] is None
    assert board["picks_made"] == 0


def test_draft_cannot_exceed_its_length(client):
    league = make_league(client, num_teams=4, my_slot=1, rounds=2)
    sid = make_session(client, league["id"])["session"]["id"]
    for i in range(8):
        assert (
            client.post(f"/api/sessions/{sid}/picks", json={"player_id": f"p{i}"}).status_code
            == 200
        )
    resp = client.post(f"/api/sessions/{sid}/picks", json={"player_id": "one-too-many"})
    assert resp.status_code == 409


def test_tags_and_notes_roundtrip(client):
    league = make_league(client)
    lid = league["id"]
    client.put(f"/api/leagues/{lid}/tags/4034", json={"tag": "target", "note": "worth a reach"})
    client.put(f"/api/leagues/{lid}/tags/7564", json={"tag": "fade"})
    tags = client.get(f"/api/leagues/{lid}/tags").json()
    assert tags["4034"]["tag"] == "target"
    assert tags["4034"]["note"] == "worth a reach"
    assert tags["7564"]["tag"] == "fade"

    # Re-tagging the same player updates in place, and null clears.
    client.put(f"/api/leagues/{lid}/tags/4034", json={"tag": "at_adp"})
    assert client.get(f"/api/leagues/{lid}/tags").json()["4034"]["tag"] == "at_adp"
    client.put(f"/api/leagues/{lid}/tags/4034", json={})
    assert client.get(f"/api/leagues/{lid}/tags").json()["4034"]["tag"] is None


def test_tags_rejected_for_unknown_league(client):
    assert client.put("/api/leagues/999/tags/1", json={"tag": "target"}).status_code == 404


def test_board_survives_a_restart(tmp_path):
    """The M2 exit criterion: 30 picks and 2 undos, then a fresh process
    against the same data dir must rebuild an identical board."""
    settings = Settings(data_dir=tmp_path / "data")
    first = TestClient(create_app(settings))
    league = make_league(first)
    sid = make_session(first, league["id"])["session"]["id"]
    for i in range(30):
        assert (
            first.post(f"/api/sessions/{sid}/picks", json={"player_id": f"p{i}"}).status_code == 200
        )
    first.post(f"/api/sessions/{sid}/picks/undo")
    first.post(f"/api/sessions/{sid}/picks/undo")
    before = first.get(f"/api/sessions/{sid}").json()
    assert before["picks_made"] == 28

    second = TestClient(create_app(settings))  # simulates a restart
    after = second.get(f"/api/sessions/{sid}").json()
    assert after == before
    assert after["drafted_player_ids"] == [f"p{i}" for i in range(28)]


def test_tags_set_before_the_draft_are_visible_during_it(tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    prep = TestClient(create_app(settings))
    league = make_league(prep)
    prep.put(f"/api/leagues/{league['id']}/tags/4034", json={"tag": "target"})

    draft_day = TestClient(create_app(settings))
    session = make_session(draft_day, league["id"])
    tags = draft_day.get(f"/api/leagues/{session['league']['id']}/tags").json()
    assert tags["4034"]["tag"] == "target"


def test_events_endpoint_requires_a_real_session(client):
    assert client.get("/api/sessions/999/events").status_code == 404


def test_pick_ownership_is_derived_from_the_slot_when_unspecified(client):
    """Plain Enter sends is_mine=null; the server decides from whose slot is on
    the clock. Otherwise muscle memory files your own pick as a rival's."""
    league = make_league(client, num_teams=12, my_slot=3)
    sid = make_session(client, league["id"])["session"]["id"]

    for i in range(2):  # slots 1 and 2
        resp = client.post(f"/api/sessions/{sid}/picks", json={"player_id": f"p{i}"})
        assert resp.json()["pick"]["is_mine"] is False

    mine = client.post(f"/api/sessions/{sid}/picks", json={"player_id": "third"}).json()
    assert mine["pick"]["slot"] == 3
    assert mine["pick"]["is_mine"] is True
    assert mine["my_player_ids"] == ["third"]


def test_explicit_ownership_still_overrides(client):
    league = make_league(client, num_teams=12, my_slot=12)
    sid = make_session(client, league["id"])["session"]["id"]
    forced = client.post(
        f"/api/sessions/{sid}/picks", json={"player_id": "x", "is_mine": True}
    ).json()
    assert forced["pick"]["slot"] == 1  # not my slot...
    assert forced["pick"]["is_mine"] is True  # ...but I said it was mine


def test_correcting_a_pick_made_several_picks_ago(client):
    """Mistyping pick 3 and noticing at pick 8 should cost one correction, not
    five undos and five re-entries while the room keeps drafting."""
    league = make_league(client, num_teams=12, my_slot=7)
    sid = make_session(client, league["id"])["session"]["id"]
    for i in range(8):
        client.post(f"/api/sessions/{sid}/picks", json={"player_id": f"p{i}"})

    fixed = client.put(f"/api/sessions/{sid}/picks/3", json={"player_id": "actually-him"})
    assert fixed.status_code == 200, fixed.text
    board = fixed.json()
    assert board["pick"]["overall_no"] == 3
    assert board["pick"]["source"] == "correction"
    # Everything after it is untouched.
    assert board["picks_made"] == 8
    assert board["drafted_player_ids"][2] == "actually-him"
    assert board["drafted_player_ids"][3] == "p3"
    # And the mistake is free to be drafted by whoever actually took him.
    assert client.post(f"/api/sessions/{sid}/picks", json={"player_id": "p2"}).status_code == 200


def test_a_correction_reassigns_ownership_by_slot(client):
    league = make_league(client, num_teams=12, my_slot=3)
    sid = make_session(client, league["id"])["session"]["id"]
    for i in range(5):
        client.post(f"/api/sessions/{sid}/picks", json={"player_id": f"p{i}"})

    # Pick 3 is my slot, so whoever ends up there is mine.
    fixed = client.put(f"/api/sessions/{sid}/picks/3", json={"player_id": "mine-really"}).json()
    assert fixed["pick"]["is_mine"] is True
    assert "mine-really" in fixed["my_player_ids"]
    assert "p2" not in fixed["my_player_ids"]


def test_correcting_to_someone_already_drafted_is_rejected(client):
    league = make_league(client)
    sid = make_session(client, league["id"])["session"]["id"]
    for i in range(4):
        client.post(f"/api/sessions/{sid}/picks", json={"player_id": f"p{i}"})
    resp = client.put(f"/api/sessions/{sid}/picks/2", json={"player_id": "p3"})
    assert resp.status_code == 409


def test_correcting_a_pick_to_itself_is_allowed(client):
    """Re-confirming the same player must not trip the duplicate check."""
    league = make_league(client)
    sid = make_session(client, league["id"])["session"]["id"]
    client.post(f"/api/sessions/{sid}/picks", json={"player_id": "same"})
    assert client.put(f"/api/sessions/{sid}/picks/1", json={"player_id": "same"}).status_code == 200


def test_correcting_a_pick_that_never_happened_is_a_404(client):
    league = make_league(client)
    sid = make_session(client, league["id"])["session"]["id"]
    client.post(f"/api/sessions/{sid}/picks", json={"player_id": "only-one"})
    assert client.put(f"/api/sessions/{sid}/picks/9", json={"player_id": "x"}).status_code == 404
    assert client.put("/api/sessions/999/picks/1", json={"player_id": "x"}).status_code == 404


def test_corrections_survive_a_restart(tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    first = TestClient(create_app(settings))
    league = make_league(first)
    sid = make_session(first, league["id"])["session"]["id"]
    for i in range(6):
        first.post(f"/api/sessions/{sid}/picks", json={"player_id": f"p{i}"})
    first.put(f"/api/sessions/{sid}/picks/2", json={"player_id": "corrected"})
    before = first.get(f"/api/sessions/{sid}").json()

    after = TestClient(create_app(settings)).get(f"/api/sessions/{sid}").json()
    assert after == before
    assert after["drafted_player_ids"][1] == "corrected"
