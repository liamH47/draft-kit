import json

import pytest

from draftkit.sources import (
    borischen_tiers,
    cbs_rankings,
    dp_playerids,
    espn_projections,
    ffcalc_adp,
    sleeper_players,
    sleeper_projections,
    yahoo_adp,
)
from draftkit.sources.base import RawPayload, SourceError
from tests.conftest import load_fixture


def test_sleeper_players_parse():
    raw = load_fixture("players/nfl")
    sleeper_players.validate(raw)
    ds = sleeper_players.parse(raw)
    by_name = {r["name"]: r for r in ds.rows}
    assert "Random Lineman" not in by_name  # non-fantasy positions filtered
    assert by_name["San Francisco 49ers"]["position"] == "DEF"
    cmc = by_name["Christian McCaffrey"]
    assert cmc["sleeper_id"] == "4034"
    assert cmc["team"] == "SF"


def test_sleeper_players_rejects_html():
    with pytest.raises(SourceError):
        sleeper_players.validate(RawPayload(b"<html>404</html>", "text/html"))


def test_sleeper_projections_parse():
    raw = load_fixture("projections/nfl")
    sleeper_projections.validate(raw)
    ds = sleeper_projections.parse(raw)
    by_id = {r["sleeper_id"]: r for r in ds.rows}
    cmc = by_id["4034"]
    assert cmc["stats"]["rush_yd"] == 1050
    assert "adp_half_ppr" in cmc["adp"]
    # adp_* fields must not leak into the raw stat line
    assert not any(k.startswith("adp_") for k in cmc["stats"])


def test_ffcalc_parse():
    raw = load_fixture("fantasyfootballcalculator")
    ffcalc_adp.validate(raw)
    ds = ffcalc_adp.parse(raw)
    by_name = {r["name"]: r for r in ds.rows}
    assert by_name["Christian McCaffrey"]["adp"] > 0
    assert by_name["Christian McCaffrey"]["bye"] is not None
    assert by_name["San Francisco Defense"]["position"] == "DEF"
    assert by_name["Brandon Aubrey"]["position"] == "K"  # FFC labels kickers PK


def test_ffcalc_rejects_error_payload():
    with pytest.raises(SourceError):
        ffcalc_adp.validate(RawPayload(b'{"status": "Error"}', "application/json"))


def test_espn_projections_parse():
    raw = load_fixture("leaguedefaults")
    espn_projections.validate(raw)
    ds = espn_projections.parse(raw)
    by_name = {r["name"]: r for r in ds.rows}
    gibbs = by_name["Jahmyr Gibbs"]
    # Raw categories mapped to Sleeper stat names, so the engine can rescore
    # under the user's own league rules.
    assert gibbs["stats"]["rush_yd"] > 500
    assert gibbs["stats"]["rec"] > 10
    assert gibbs["applied_total"] > 100
    # DEF has no mapped categories: applied_total is the fallback.
    defense = next(r for r in ds.rows if r["position"] == "DEF")
    assert defense["stats"] == {} and defense["applied_total"] > 0
    # A player with only weekly stats entries has no season projection.
    assert all(r["name"] != "Long Snapper" for r in ds.rows)


def test_espn_projections_rejects_the_filterless_shape():
    # Without a parseable X-Fantasy-Filter, ESPN returns a bare list.
    with pytest.raises(SourceError, match="filter ignored"):
        espn_projections.validate(RawPayload(b'[{"id": 1}]', "application/json"))


def test_cbs_parse():
    raw = load_fixture("cbssports")
    cbs_rankings.validate(raw)
    ds = cbs_rankings.parse(raw)
    assert ds.rows[0]["rank"] == 1.0
    assert all(r["cbs_id"] for r in ds.rows)  # the id-less row was skipped
    assert all(r["position"] in {"QB", "RB", "WR", "TE", "K", "DEF"} for r in ds.rows)


def test_cbs_rejects_an_empty_rankings_body():
    with pytest.raises(SourceError, match="no players"):
        cbs_rankings.validate(RawPayload(b'{"body": {"rankings": {}}}', "application/json"))


def test_yahoo_parse():
    raw = load_fixture("pub-api-ro")
    yahoo_adp.validate(raw)
    ds = yahoo_adp.parse(raw)
    with_adp = [r for r in ds.rows if r["adp"] is not None]
    assert len(with_adp) >= 3
    top = min(with_adp, key=lambda r: r["adp"])
    assert top["yahoo_id"] and top["position"] and top["average_cost"] is not None
    # Yahoo's "-" sentinel for the deep tail becomes None, not a crash.
    assert any(r["adp"] is None for r in ds.rows)


def test_yahoo_rejects_a_payload_without_fantasy_content():
    with pytest.raises(SourceError, match="fantasy_content"):
        yahoo_adp.validate(RawPayload(b'{"error": "nope"}', "application/json"))


def test_borischen_parse():
    raw = load_fixture("fftiers")
    borischen_tiers.validate(raw)
    ds = borischen_tiers.parse(raw)
    assert len(ds.rows) > 50
    first = ds.rows[0]
    assert first["tier"] == 1
    assert first["rank"] == 1
    assert first["position"] in {"QB", "RB", "WR", "TE", "K", "DEF"}


def test_dp_parse():
    raw = load_fixture("db_playerids")
    dp_playerids.validate(raw)
    ds = dp_playerids.parse(raw)
    by_merge = {r["merge_name"]: r for r in ds.rows}
    assert by_merge["christian mccaffrey"]["sleeper_id"] == "4034"
    assert by_merge["christian mccaffrey"]["espn_id"]
    # every platform join key the pool uses must survive the crosswalk
    assert by_merge["christian mccaffrey"]["cbs_id"]
    assert by_merge["christian mccaffrey"]["yahoo_id"]
    assert by_merge["brandon aubrey"]["position"] == "K"  # PK normalized


def test_dp_rejects_github_error_page():
    with pytest.raises(SourceError):
        dp_playerids.validate(RawPayload(b"<!DOCTYPE html><html>...", "text/html"))


def test_borischen_keeps_expert_consensus_columns():
    """Avg.Rank and Std.Dev are the expert signal; they were being discarded."""
    raw = load_fixture("fftiers")
    rows = {r["name"]: r for r in borischen_tiers.parse(raw).rows}
    top = rows["Jahmyr Gibbs"]
    assert top["expert_rank"] > 0
    assert top["expert_stdev"] is not None
    assert top["expert_best"] <= top["expert_worst"]


def test_borischen_tolerates_missing_or_unparseable_columns():
    """Columns come and go between Boris Chen's files; absence is not failure."""
    body = (
        b'"Rank","Player.Name","Tier","Position","Best.Rank","Worst.Rank","Avg.Rank","Std.Dev"\n'
        b'1,"Someone","1","RB",1,3,"NA",""\n'
        b'2,"Other","1","WR",1,4,"not-a-number",0.5\n'
    )
    rows = borischen_tiers.parse(RawPayload(body=body, content_type="text/csv")).rows
    assert rows[0]["expert_rank"] is None
    assert rows[0]["expert_stdev"] is None
    assert rows[1]["expert_rank"] is None  # unparseable, not a crash
    assert rows[1]["expert_stdev"] == 0.5


def test_yahoo_skips_rows_without_an_id_or_a_name():
    """Yahoo pads its pages with fragments that are not players."""
    payload = {
        "fantasy_content": {
            "game": [
                {"game_key": "470"},
                {
                    "players": {
                        "0": {
                            "player": [[{"player_id": "1"}, {"name": {"full": "Real Player"}}], []]
                        },
                        "1": {"player": [[{"name": {"full": "No Id"}}], []]},
                        "2": {"player": [[{"player_id": "3"}], []]},
                        "3": "not a mapping at all",
                        "count": 4,
                    }
                },
            ]
        }
    }
    ds = yahoo_adp.parse(RawPayload(json.dumps(payload).encode(), "application/json"))
    assert [r["name"] for r in ds.rows] == ["Real Player"]


def test_yahoo_tolerates_a_page_with_no_player_block():
    """Yahoo wraps players in a positional list; an error or empty page has
    the wrapper but no block, which must parse to nothing rather than raise."""
    payload = {"fantasy_content": {"game": [{"game_key": "470"}]}}
    ds = yahoo_adp.parse(RawPayload(json.dumps(payload).encode(), "application/json"))
    assert ds.rows == []
