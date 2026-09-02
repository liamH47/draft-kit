"""Bringing a ranking list in by hand, end to end.

The user's own lists are the answer to every source we cannot fetch — the paid
ones, the ones behind a login, the one somebody posts as a PDF. What matters
here is that a paste either lands completely or says exactly which names it
lost. A list that quietly arrives fourteen players short is the failure that
gets discovered in round four.
"""

import json

from fastapi.testclient import TestClient

from draftkit.config import Settings
from draftkit.main import create_app
from draftkit.snapshots.store import SnapshotStore
from draftkit.sources.base import RawPayload
from tests.conftest import _URL_TO_FIXTURE

# Names that exist in the recorded Sleeper fixture, so they really resolve.
PASTE = """
2026 Cheat Sheet
Rank  Player  Pos  Team
1.  Christian McCaffrey  RB  SF
2.  Bijan Robinson  RB  ATL
3.  Ja'Marr Chase  WR  CIN
Page 1
"""


def make_client(tmp_path, fetcher) -> TestClient:
    app = create_app(Settings(data_dir=tmp_path / "data"))
    app.state.snapshot_store = SnapshotStore(tmp_path / "data" / "snapshots", fetcher)
    return TestClient(app)


def test_a_pasted_list_resolves_and_comes_back_with_its_misses(tmp_path, fixture_fetcher):
    client = make_client(tmp_path, fixture_fetcher)
    resp = client.put("/api/rankings/my-guys", json={"text": PASTE + "99. Nobody At All WR CIN\n"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 4
    assert body["matched"] == 3
    assert body["unmatched"] == ["Nobody At All"]

    rows = client.get("/api/rankings/my-guys").json()["rows"]
    # Every row carried a number and they ascend, so the list's own numbering
    # is kept rather than being renumbered by position.
    assert [r["rank"] for r in rows] == [1, 2, 3, 99]
    # The miss is STORED, not dropped: the user has to be able to see it.
    assert rows[3]["player_id"] is None
    assert rows[3]["source_name"] == "Nobody At All"

    summary = client.get("/api/rankings").json()["lists"]
    assert summary == [
        {
            "list_name": "my-guys",
            "total": 4,
            "matched": 3,
            "updated_at": rows[0]["updated_at"],
            # A fresh list counts level with ESPN and CBS until told otherwise.
            "weight": 1.0,
        }
    ]


def test_a_list_reaches_the_board_as_a_consensus_input(tmp_path, fixture_fetcher):
    """A pasted list is not decoration — it joins the published lists in the
    consensus rank the board shows itself against."""
    client = make_client(tmp_path, fixture_fetcher)
    before = {p["name"]: p for p in client.get("/api/players").json()["players"]}
    client.put("/api/rankings/mine", json={"text": PASTE})
    after = {p["name"]: p for p in client.get("/api/players").json()["players"]}

    cmc = after["Christian McCaffrey"]
    assert cmc["rank_by_source"]["custom:mine"] == 1
    assert cmc["consensus_rank"] != before["Christian McCaffrey"]["consensus_rank"]


def test_repasting_a_list_replaces_it_rather_than_merging(tmp_path, fixture_fetcher):
    """A republished cheat sheet is a correction. Merging would leave last
    week's players sitting at ranks the new list no longer has."""
    client = make_client(tmp_path, fixture_fetcher)
    client.put("/api/rankings/mine", json={"text": PASTE})
    client.put("/api/rankings/mine", json={"text": "1. Ja'Marr Chase WR CIN"})
    rows = client.get("/api/rankings/mine").json()["rows"]
    assert [r["source_name"] for r in rows] == ["Ja'Marr Chase"]


def test_a_repaste_shows_up_on_the_board_immediately(tmp_path, fixture_fetcher):
    """The pool caches per configuration and the list is part of that
    configuration, so an import that did not clear the cache would not show up
    until it lapsed — five minutes into a draft."""
    client = make_client(tmp_path, fixture_fetcher)
    client.put("/api/rankings/mine", json={"text": PASTE})
    client.put("/api/rankings/mine", json={"text": "1. Ja'Marr Chase WR CIN"})
    by_name = {p["name"]: p for p in client.get("/api/players").json()["players"]}
    assert "custom:mine" not in by_name["Christian McCaffrey"]["rank_by_source"]
    assert by_name["Ja'Marr Chase"]["rank_by_source"]["custom:mine"] == 1


def test_a_name_with_no_position_still_resolves(tmp_path, fixture_fetcher):
    """A cheat sheet that is one column of names is a normal cheat sheet."""
    client = make_client(tmp_path, fixture_fetcher)
    body = client.put("/api/rankings/bare", json={"text": "Christian McCaffrey"}).json()
    assert body["matched"] == 1


def test_deleting_a_list_removes_it_and_its_column(tmp_path, fixture_fetcher):
    client = make_client(tmp_path, fixture_fetcher)
    client.put("/api/rankings/mine", json={"text": PASTE})
    assert client.delete("/api/rankings/mine").json()["removed"] == 3
    assert client.get("/api/rankings/mine").status_code == 404
    assert client.delete("/api/rankings/mine").status_code == 404
    by_name = {p["name"]: p for p in client.get("/api/players").json()["players"]}
    assert "custom:mine" not in by_name["Christian McCaffrey"]["rank_by_source"]


def test_a_paste_with_no_players_in_it_is_refused(tmp_path, fixture_fetcher):
    client = make_client(tmp_path, fixture_fetcher)
    resp = client.put("/api/rankings/junk", json={"text": "Page 1 of 4\n-----\n12"})
    assert resp.status_code == 422
    assert "no player names" in resp.json()["detail"]


def test_a_list_name_that_would_poison_a_source_key_is_refused(tmp_path, fixture_fetcher):
    client = make_client(tmp_path, fixture_fetcher)
    for bad in (" ", "a" * 41, "has:colon", ".leading-dot"):
        resp = client.put(f"/api/rankings/{bad}", json={"text": PASTE})
        assert resp.status_code == 422, bad


def test_an_empty_paste_is_refused_by_the_schema(tmp_path, fixture_fetcher):
    client = make_client(tmp_path, fixture_fetcher)
    assert client.put("/api/rankings/mine", json={"text": ""}).status_code == 422


# --- the file beside the database -------------------------------------------


def test_every_write_is_mirrored_to_a_file(tmp_path, fixture_fetcher):
    client = make_client(tmp_path, fixture_fetcher)
    client.put("/api/rankings/mine", json={"text": PASTE})
    mirror = tmp_path / "data" / "rankings.json"
    payload = json.loads(mirror.read_text(encoding="utf-8"))
    assert [r["source_name"] for r in payload["mine"]] == [
        "Christian McCaffrey",
        "Bijan Robinson",
        "Ja'Marr Chase",
    ]


def test_the_mirror_rebuilds_a_database_that_was_deleted(tmp_path, fixture_fetcher):
    """The recovery path: the file is the copy that still has your cheat sheet
    when the database is gone, moved, or was started from the wrong folder."""
    app = create_app(Settings(data_dir=tmp_path / "data"))
    app.state.snapshot_store = SnapshotStore(tmp_path / "data" / "snapshots", fixture_fetcher)
    client = TestClient(app)
    client.put("/api/rankings/mine", json={"text": PASTE})
    app.state.db.execute("DELETE FROM custom_ranking")
    app.state.db.commit()
    assert client.get("/api/rankings").json()["lists"] == []

    restored = client.post("/api/rankings/restore").json()
    assert restored["restored"] == 3
    rows = client.get("/api/rankings/mine").json()["rows"]
    assert rows[0]["source_name"] == "Christian McCaffrey"
    assert rows[0]["player_id"] == "4034"


def test_restore_says_so_when_there_is_nothing_to_restore_from(tmp_path, fixture_fetcher):
    client = make_client(tmp_path, fixture_fetcher)
    assert client.post("/api/rankings/restore").status_code == 404


def test_restore_refuses_a_file_that_is_not_a_ranking_file(tmp_path, fixture_fetcher):
    client = make_client(tmp_path, fixture_fetcher)
    mirror = tmp_path / "data" / "rankings.json"
    mirror.parent.mkdir(parents=True, exist_ok=True)
    mirror.write_text("{not json", encoding="utf-8")
    assert client.post("/api/rankings/restore").status_code == 422
    mirror.write_text("[1, 2, 3]", encoding="utf-8")
    assert client.post("/api/rankings/restore").status_code == 422


def test_a_mirror_that_cannot_be_written_never_costs_the_list(
    tmp_path, fixture_fetcher, monkeypatch
):
    """The database already holds it. A read-only data directory must lose the
    convenience copy, not the import."""
    from draftkit.api import rankings

    def explode(*args, **kwargs):
        raise OSError("read-only")

    monkeypatch.setattr(rankings.repo, "get_ranking_lists", explode)
    client = make_client(tmp_path, fixture_fetcher)
    assert client.put("/api/rankings/mine", json={"text": PASTE}).json()["matched"] == 3


def test_a_list_still_imports_when_the_crosswalk_is_unavailable(tmp_path):
    """Names resolve against the Sleeper universe; the crosswalk only adds
    ids. Losing it costs precision, never the import."""

    def fetch(spec):
        for fragment, path, content_type in _URL_TO_FIXTURE:
            if fragment in spec.url:
                if fragment == "db_playerids":
                    raise ConnectionError("crosswalk down")
                return RawPayload(body=path.read_bytes(), content_type=content_type)
        raise AssertionError(f"no fixture for {spec.url}")

    client = make_client(tmp_path, fetch)
    assert client.put("/api/rankings/mine", json={"text": PASTE}).json()["matched"] == 3


# --- how far you trust a list -----------------------------------------------
#
# The default is "as much as ESPN". These cover the two ends of moving it: a
# list you trust more than the published ones, and one you want to SEE without
# letting it vote. Both must reach the consensus column and neither may reach
# the score.


def _consensus(client, name="Christian McCaffrey"):
    return {p["name"]: p for p in client.get("/api/players").json()["players"]}[name]


def test_weighting_a_list_up_pulls_the_consensus_toward_it(tmp_path, fixture_fetcher):
    """The point of the feature: a list you trust more than ESPN's should move
    the number the board shows itself against, by the amount you said."""
    client = make_client(tmp_path, fixture_fetcher)
    client.put("/api/rankings/mine", json={"text": PASTE})
    level = _consensus(client)["consensus_rank"]

    resp = client.patch("/api/rankings/mine", json={"weight": 8})
    assert resp.status_code == 200
    assert resp.json() == {"name": "mine", "weight": 8.0, "rows": 3}

    heavy = _consensus(client)
    # The list has him at 1, so leaning on it can only pull the consensus down
    # toward 1 — and it must actually move, not merely be allowed to.
    assert heavy["rank_by_source"]["custom:mine"] == 1
    assert heavy["consensus_rank"] < level
    assert client.get("/api/rankings").json()["lists"][0]["weight"] == 8.0


def test_weight_zero_shows_a_list_without_letting_it_vote(tmp_path, fixture_fetcher):
    """The other end: keep the column, drop the vote. A list at 0 must leave
    the consensus exactly where it was before the list existed."""
    client = make_client(tmp_path, fixture_fetcher)
    without = _consensus(client)["consensus_rank"]
    client.put("/api/rankings/mine", json={"text": PASTE})
    assert _consensus(client)["consensus_rank"] != without

    client.patch("/api/rankings/mine", json={"weight": 0})
    silenced = _consensus(client)
    assert silenced["consensus_rank"] == without
    # Still there to read — silenced is not deleted.
    assert silenced["rank_by_source"]["custom:mine"] == 1


def test_reweighting_shows_up_on_the_board_immediately(tmp_path, fixture_fetcher):
    """Same trap as an import: the pool caches per configuration, and a weight
    is part of that configuration. Without a cache clear the new weight would
    arrive five minutes into the draft."""
    client = make_client(tmp_path, fixture_fetcher)
    client.put("/api/rankings/mine", json={"text": PASTE})
    before = _consensus(client)["consensus_rank"]
    client.patch("/api/rankings/mine", json={"weight": 10})
    assert _consensus(client)["consensus_rank"] != before


def test_weight_never_reaches_the_score_or_the_room_forecast(tmp_path, fixture_fetcher):
    """Trusting a list harder does not make the ROOM follow it, and a ranking
    is not a projection. Only the consensus display may move."""
    client = make_client(tmp_path, fixture_fetcher)
    client.put("/api/rankings/mine", json={"text": PASTE})
    before = _consensus(client)
    client.patch("/api/rankings/mine", json={"weight": 10})
    after = _consensus(client)
    assert after["consensus_rank"] != before["consensus_rank"]
    assert after["value"] == before["value"]
    assert after["rank"] == before["rank"]
    assert after["adp"] == before["adp"]


def test_a_repaste_keeps_the_weight_you_set(tmp_path, fixture_fetcher):
    """Re-pasting means the publisher updated the list, not that you stopped
    trusting it. Resetting the weight here would be silent."""
    client = make_client(tmp_path, fixture_fetcher)
    client.put("/api/rankings/mine", json={"text": PASTE})
    client.patch("/api/rankings/mine", json={"weight": 3})
    assert client.put("/api/rankings/mine", json={"text": PASTE}).json()["weight"] == 3.0
    assert client.get("/api/rankings").json()["lists"][0]["weight"] == 3.0


def test_reweighting_a_list_that_is_not_there_says_so(tmp_path, fixture_fetcher):
    """A typo in the name must not silently do nothing."""
    client = make_client(tmp_path, fixture_fetcher)
    assert client.patch("/api/rankings/nope", json={"weight": 2}).status_code == 404


def test_a_weight_outside_the_band_is_refused(tmp_path, fixture_fetcher):
    client = make_client(tmp_path, fixture_fetcher)
    client.put("/api/rankings/mine", json={"text": PASTE})
    for bad in (-1, 10.5):
        assert client.patch("/api/rankings/mine", json={"weight": bad}).status_code == 422, bad


def test_the_weight_survives_the_mirror(tmp_path, fixture_fetcher):
    """The file beside the database is the recovery path, so it has to carry
    the weight too — otherwise restoring quietly hands every list back at 1."""
    app = create_app(Settings(data_dir=tmp_path / "data"))
    app.state.snapshot_store = SnapshotStore(tmp_path / "data" / "snapshots", fixture_fetcher)
    client = TestClient(app)
    client.put("/api/rankings/mine", json={"text": PASTE})
    client.patch("/api/rankings/mine", json={"weight": 4})
    app.state.db.execute("DELETE FROM custom_ranking")
    app.state.db.commit()

    client.post("/api/rankings/restore")
    assert client.get("/api/rankings").json()["lists"][0]["weight"] == 4.0


def test_a_mirror_written_before_weights_existed_restores_at_the_default(tmp_path, fixture_fetcher):
    """Somebody's rankings.json predates this column. It must still restore."""
    client = make_client(tmp_path, fixture_fetcher)
    mirror = tmp_path / "data" / "rankings.json"
    mirror.parent.mkdir(parents=True, exist_ok=True)
    row = {"rank": 1, "player_id": "4034", "source_name": "Christian McCaffrey"}
    mirror.write_text(json.dumps({"old": [row]}), encoding="utf-8")
    assert client.post("/api/rankings/restore").json()["restored"] == 1
    assert client.get("/api/rankings").json()["lists"][0]["weight"] == 1.0
