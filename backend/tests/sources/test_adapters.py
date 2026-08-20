import pytest

from draftkit.sources import (
    borischen_tiers,
    dp_playerids,
    ffcalc_adp,
    sleeper_players,
    sleeper_projections,
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
    assert by_name["San Francisco Defense"]["position"] == "DEF"  # DST normalized


def test_ffcalc_rejects_error_payload():
    with pytest.raises(SourceError):
        ffcalc_adp.validate(RawPayload(b'{"status": "Error"}', "application/json"))


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
