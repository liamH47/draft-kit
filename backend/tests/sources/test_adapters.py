import json

import pytest

from draftkit.sources import (
    borischen_tiers,
    cbs_rankings,
    dp_playerids,
    espn_projections,
    ffcalc_adp,
    mfl_adp,
    sleeper_players,
    sleeper_projections,
    sleeper_trending,
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


# --- MyFantasyLeague --------------------------------------------------------


def test_mfl_parse():
    raw = load_fixture("myfantasyleague")
    mfl_adp.validate(raw)
    ds = mfl_adp.parse(raw)
    assert ds.rows
    first = ds.rows[0]
    assert first["mfl_id"] and isinstance(first["mfl_id"], str)
    assert first["adp"] > 0
    # Every row carries the shape of its sample, so a price drawn from nine
    # drafts can be told apart from one drawn from two hundred.
    assert first["times_drafted"] >= 1
    assert first["earliest"] <= first["adp"] <= first["latest"]


def test_mfl_request_maps_scoring_to_its_own_reception_flag():
    assert "IS_PPR=1" in mfl_adp.request({"format": "ppr", "year": 2026}).url
    assert "IS_PPR=0" in mfl_adp.request({"format": "standard", "year": 2026}).url
    # MFL has no half-PPR bucket, so half-PPR reads the combined sample.
    assert "IS_PPR=-1" in mfl_adp.request({"format": "half_ppr", "year": 2026}).url
    assert "IS_PPR=-1" in mfl_adp.request({"year": 2026}).url


def test_mfl_rejects_a_payload_that_is_not_its_own():
    with pytest.raises(SourceError):
        mfl_adp.validate(RawPayload(b"<html>down for maintenance</html>", "text/html"))
    with pytest.raises(SourceError):
        mfl_adp.validate(RawPayload(b'{"error": "bad request"}', "application/json"))
    with pytest.raises(SourceError):
        mfl_adp.validate(RawPayload(b'{"adp": {"player": []}}', "application/json"))


def test_mfl_collapses_a_single_row_result_to_a_list():
    """MFL returns a bare object rather than a one-element list when only one
    player comes back. Iterating that would walk the dict's KEYS."""
    body = b'{"adp": {"player": {"id": "16162", "averagePick": "2.10", "rank": "1"}}}'
    ds = mfl_adp.parse(RawPayload(body, "application/json"))
    assert [r["mfl_id"] for r in ds.rows] == ["16162"]
    assert ds.rows[0]["earliest"] is None  # absent fields stay absent, not zero


def test_mfl_skips_rows_with_no_id_or_no_price():
    body = (
        b'{"adp": {"player": ['
        b'{"averagePick": "2.10"},'
        b'{"id": "999", "averagePick": "-"},'
        b'{"id": "16162", "averagePick": "3.5"}]}}'
    )
    ds = mfl_adp.parse(RawPayload(body, "application/json"))
    assert [r["mfl_id"] for r in ds.rows] == ["16162"]


# --- Sleeper trending -------------------------------------------------------


def test_sleeper_trending_parse():
    raw = load_fixture("trending/add")
    sleeper_trending.validate(raw)
    ds = sleeper_trending.parse(raw)
    assert ds.rows
    assert all(isinstance(r["sleeper_id"], str) for r in ds.rows)
    assert all(r["trend_count"] > 0 for r in ds.rows)


def test_sleeper_trending_request_names_the_kind_it_was_asked_for():
    assert "trending/add" in sleeper_trending.request({"kind": "add"}).url
    assert "trending/drop" in sleeper_trending.request({"kind": "drop"}).url
    assert "trending/add" in sleeper_trending.request({}).url
    assert "lookback_hours=48" in sleeper_trending.request({"lookback_hours": 48}).url


def test_sleeper_trending_refuses_a_kind_that_is_not_a_kind():
    """A typo here would silently fetch a 404 page and cost the column. Fail
    at the request, where the mistake is."""
    with pytest.raises(ValueError, match="trending kind"):
        sleeper_trending.request({"kind": "adds"})


def test_sleeper_trending_rejects_a_payload_that_is_not_a_list():
    with pytest.raises(SourceError):
        sleeper_trending.validate(RawPayload(b"<html>nope</html>", "text/html"))
    with pytest.raises(SourceError):
        sleeper_trending.validate(RawPayload(b"not json", "application/json"))
    with pytest.raises(SourceError):
        sleeper_trending.validate(RawPayload(b"[]", "application/json"))
    with pytest.raises(SourceError):
        sleeper_trending.validate(RawPayload(b'{"count": 1}', "application/json"))


def test_sleeper_trending_skips_rows_missing_an_id_or_a_count():
    body = b'[{"count": 10}, {"player_id": "1"}, {"player_id": "2", "count": "lots"}, '
    body += b'{"player_id": "3", "count": 7}]'
    ds = sleeper_trending.parse(RawPayload(body, "application/json"))
    assert ds.rows == [{"sleeper_id": "3", "trend_count": 7}]


# --- the crosswalk now carries the key MFL speaks ---------------------------


def test_dp_carries_the_mfl_id():
    raw = load_fixture("db_playerids")
    ds = dp_playerids.parse(raw)
    assert any(r["mfl_id"] for r in ds.rows), "no row carried an mfl_id"


# --- Sleeper's injury and depth-chart fields --------------------------------


def test_sleeper_players_carries_injury_and_depth_chart():
    """These were already inside the payload we download daily and were being
    thrown away, which is how a man on IR could top the board."""
    body = json.dumps(
        {
            "1": {
                "player_id": "1",
                "full_name": "Hurt Guy",
                "position": "RB",
                "team": "SF",
                "injury_status": "IR",
                "injury_body_part": "Knee - ACL",
                "depth_chart_order": 2,
            },
            "2": {"player_id": "2", "full_name": "Fit Guy", "position": "RB", "team": "SF"},
        }
    ).encode()
    ds = sleeper_players.parse(RawPayload(body, "application/json"))
    by_name = {r["name"]: r for r in ds.rows}
    assert by_name["Hurt Guy"]["injury_status"] == "IR"
    assert by_name["Hurt Guy"]["injury_body_part"] == "Knee - ACL"
    assert by_name["Hurt Guy"]["depth_chart_order"] == 2
    assert by_name["Fit Guy"]["injury_status"] is None


def test_fantasypros_parse():
    """ECR arrives inside a <script> on an HTML page rather than from an API,
    so the parse starts by finding a blob in markup. Everything downstream
    depends on that having worked."""
    from draftkit.sources import fantasypros

    raw = load_fixture("fantasypros")
    fantasypros.validate(raw)
    ds = fantasypros.parse(raw)
    by_id = {r["fantasypros_id"]: r for r in ds.rows}

    gibbs = by_id["22968"]
    assert gibbs["name"] == "Jahmyr Gibbs"
    assert gibbs["position"] == "RB"
    assert gibbs["team"] == "DET"
    assert gibbs["rank"] == 1.0
    assert gibbs["bye"] == 6
    # The spread across the experts who ranked him, which is what makes a
    # confident-looking average readable.
    assert gibbs["expert_best"] <= gibbs["expert_rank"] <= gibbs["expert_worst"]
    assert gibbs["expert_stdev"] > 0

    # DST is their spelling; DEF is ours, everywhere else in the codebase.
    texans = by_id["8120"]
    assert texans["position"] == "DEF"
    assert texans["name"] == "Houston Texans"


def test_fantasypros_request_serves_a_different_page_per_scoring_format():
    """Standard, half-PPR and PPR are genuinely different lists — hundreds of
    players sit at a different rank — so the format must reach the URL."""
    from draftkit.sources import fantasypros

    urls = {f: fantasypros.request({"format": f}).url for f in ("standard", "half_ppr", "ppr")}
    assert len(set(urls.values())) == 3
    assert "half-point-ppr" in urls["half_ppr"]
    # An unspecified format must not silently become standard scoring.
    assert fantasypros.request({}).url == urls["half_ppr"]


def test_fantasypros_rejects_a_page_it_does_not_recognise():
    """This adapter scrapes markup, so it is the one most likely to be broken
    by a redesign. It has to fail loudly: a near-empty list parsed from a
    changed page would cost the column silently."""
    from draftkit.sources import fantasypros
    from draftkit.sources.base import RawPayload

    cases = {
        "wrong content type": RawPayload(b'var ecrData = {"players":[1]};', "application/json"),
        "no blob at all": RawPayload(b"<html><body>maintenance</body></html>", "text/html"),
        "blob is not json": RawPayload(
            b"<html><script>var ecrData = {nope};</script>", "text/html"
        ),
        "blob has no players": RawPayload(
            b'<html><script>var ecrData = {"players":[]};</script>', "text/html"
        ),
        "blob is not an object": RawPayload(
            b"<html><script>var ecrData = {};</script>", "text/html"
        ),
    }
    for label, raw in cases.items():
        with pytest.raises(SourceError):
            fantasypros.validate(raw)
            raise AssertionError(label)


def test_fantasypros_skips_rows_that_carry_no_rank():
    """A player listed on the page but not yet ranked is not a rank of zero."""
    from draftkit.sources import fantasypros
    from draftkit.sources.base import RawPayload

    blob = {
        "players": [
            {
                "player_id": 1,
                "player_name": "Ranked Man",
                "player_position_id": "WR",
                "rank_ecr": 4,
                "tier": 2,
                "player_bye_week": "9",
                "rank_ave": "4.1",
                "rank_std": "1.0",
                "rank_min": "3",
                "rank_max": "6",
            },
            {"player_id": 2, "player_name": "Unranked Man", "rank_ecr": None},
            {"player_id": None, "player_name": "No Id", "rank_ecr": 5},
        ]
    }
    raw = RawPayload(f"<script>var ecrData = {json.dumps(blob)};</script>".encode(), "text/html")
    rows = fantasypros.parse(raw).rows
    assert [r["fantasypros_id"] for r in rows] == ["1"]


def test_fantasypros_tolerates_a_missing_expert_spread():
    """One expert ranking a player leaves the spread columns empty strings.
    Absent has to stay absent — zero is a real rank."""
    from draftkit.sources import fantasypros
    from draftkit.sources.base import RawPayload

    blob = {
        "players": [
            {
                "player_id": 7,
                "player_name": "Thin Data",
                "player_position_id": "TE",
                "player_team_id": None,
                "rank_ecr": 88,
                "tier": None,
                "player_bye_week": "",
                "rank_ave": "",
                "rank_std": None,
                "rank_min": "not a number",
                "rank_max": "90",
            }
        ]
    }
    raw = RawPayload(f"<script>var ecrData = {json.dumps(blob)};</script>".encode(), "text/html")
    (row,) = fantasypros.parse(raw).rows
    assert row["tier"] is None
    assert row["bye"] is None
    assert row["team"] is None
    assert row["expert_rank"] is None
    assert row["expert_stdev"] is None
    assert row["expert_best"] is None  # unparseable, not zero
    assert row["expert_worst"] == 90.0


def test_fantasypros_serves_a_different_board_for_superflex():
    """A superflex slot is a second QB in all but name, and the consensus
    reprices quarterbacks violently for it — Josh Allen sat at ECR 1 on the
    superflex board and ECR 28 on the 1-QB board of the same date. Serving the
    1-QB list into a superflex draft is worse than serving none, because it
    looks authoritative while being wrong about the whole first round."""
    from draftkit.sources import fantasypros

    for fmt in ("standard", "half_ppr", "ppr"):
        one_qb = fantasypros.request({"format": fmt}).url
        superflex = fantasypros.request({"format": fmt, "superflex": True}).url
        assert one_qb != superflex, fmt
        assert "superflex" in superflex, fmt
        assert "superflex" not in one_qb, fmt
    # Absent or falsey means the ordinary board, so a league saved before
    # superflex existed keeps reading the list it always read.
    assert (
        fantasypros.request({"format": "ppr"}).url
        == fantasypros.request({"format": "ppr", "superflex": False}).url
    )
