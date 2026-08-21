"""How the multi-source pool joins: blended points, extra ADP markets and
ranking lists, and the bye-week fallback chain.

Each of these sources is optional by construction — the pool must build with
any subset of them, because on draft night an unreachable feed costs its
columns and nothing else.
"""

import json
from pathlib import Path

import pytest

from draftkit.models.league import LeagueConfig, ScoringSettings
from draftkit.pool import build_pool
from draftkit.snapshots.store import SnapshotStore
from draftkit.sources.base import RawPayload
from tests.conftest import _URL_TO_FIXTURE


def league() -> LeagueConfig:
    return LeagueConfig(scoring=ScoringSettings.preset("half_ppr"))


def fetcher_without(*fragments: str):
    """Serve the recorded fixtures, but fail for the named sources."""

    def fetch(spec):
        for fragment, path, content_type in _URL_TO_FIXTURE:
            if fragment in spec.url:
                if fragment in fragments:
                    raise ConnectionError(f"{fragment} is down")
                return RawPayload(body=path.read_bytes(), content_type=content_type)
        raise AssertionError(f"no fixture for {spec.url}")

    return fetch


def build(tmp_path, fetch) -> dict:
    store = SnapshotStore(tmp_path / "snaps", fetch)
    result = build_pool(store, league(), season=2026, scoring_preset="half_ppr")
    return {p.name: p for p in result.players}


def test_points_blend_the_projection_sources(tmp_path, fixture_fetcher):
    by_name = build(tmp_path, fixture_fetcher)
    cmc = by_name["Christian McCaffrey"]
    assert cmc.extra["points.sleeper"] != cmc.extra["points.espn"]
    assert cmc.points == pytest.approx(
        (cmc.extra["points.sleeper"] + cmc.extra["points.espn"]) / 2, abs=0.01
    )


def test_a_player_only_one_source_projects_keeps_that_projection(tmp_path):
    """ESPN covers a few hundred players; Sleeper covers thousands. A player
    outside ESPN's list must not be blended toward zero."""
    solo = build(tmp_path, fetcher_without("leaguedefaults"))
    both = build(tmp_path / "b", None or fetcher_without())
    name = "Christian McCaffrey"
    assert "points.espn" not in solo[name].extra
    assert solo[name].points != both[name].points


def test_yahoo_and_cbs_add_a_market_and_a_list(tmp_path, fixture_fetcher):
    by_name = build(tmp_path, fixture_fetcher)
    gibbs = by_name["Jahmyr Gibbs"]
    assert "yahoo" in gibbs.adp_by_source
    assert "cbs" in gibbs.rank_by_source
    assert gibbs.extra["yahoo.average_cost"] > 0
    assert gibbs.consensus_rank is not None


def test_the_pool_still_builds_when_every_optional_source_is_down(tmp_path):
    """The spine is Sleeper players + projections; everything else is optional."""
    by_name = build(
        tmp_path,
        fetcher_without(
            "leaguedefaults",
            "cbssports",
            "pub-api-ro",
            "fantasyfootballcalculator",
            "fftiers",
            "lm-api-reads",
            "db_playerids",
        ),
    )
    assert len(by_name) >= 15
    cmc = by_name["Christian McCaffrey"]
    assert cmc.points > 0
    assert cmc.adp_by_source == {"sleeper": pytest.approx(cmc.adp_by_source.get("sleeper", 0))}


def test_bye_falls_back_past_a_source_that_lacks_the_player(tmp_path, fixture_fetcher):
    """FFC lists ~250 players; Yahoo and CBS fill byes it never carries."""
    assert build(tmp_path, fixture_fetcher)["Jahmyr Gibbs"].bye is not None
    without_ffc = build(tmp_path / "b", fetcher_without("fantasyfootballcalculator"))
    assert without_ffc["Jahmyr Gibbs"].bye is not None  # Yahoo/CBS carried it


def test_the_yahoo_walk_stops_at_a_page_with_no_adp(tmp_path):
    """Yahoo pages 25 at a time and the tail has no ADP at all. Walking to the
    hard cap would cost 16 requests where 1 will do."""
    calls = []
    page = json.loads(
        (Path(__file__).parent / "fixtures" / "yahoo" / "draft_analysis.json").read_text()
    )
    players = page["fantasy_content"]["game"][1]["players"]
    for key, wrapped in players.items():
        if key == "count":
            continue
        for fragment in wrapped["player"][1:]:
            if isinstance(fragment, dict) and "draft_analysis" in fragment:
                for item in fragment["draft_analysis"]:
                    if isinstance(item, dict) and "average_pick" in item:
                        item["average_pick"] = "-"
    empty = json.dumps(page).encode()

    def fetch(spec):
        for fragment, path, content_type in _URL_TO_FIXTURE:
            if fragment in spec.url:
                if fragment == "pub-api-ro":
                    calls.append(spec.url)
                    return RawPayload(body=empty, content_type=content_type)
                return RawPayload(body=path.read_bytes(), content_type=content_type)
        raise AssertionError(f"no fixture for {spec.url}")

    build(tmp_path, fetch)
    assert len(calls) == 1


def test_rows_we_cannot_resolve_are_skipped_not_crashed_on(tmp_path):
    """CBS and the projection feeds list players our universe never heard of
    (camp bodies, practice-squad call-ups). They are dropped quietly."""

    def fetch(spec):
        for fragment, path, content_type in _URL_TO_FIXTURE:
            if fragment not in spec.url:
                continue
            body = path.read_bytes()
            if fragment == "cbssports":
                payload = json.loads(body)
                payload["body"]["rankings"]["players"].append(
                    {"id": "999999", "fullname": "Nobody Atall", "rank": "300", "position": "WR"}
                )
                body = json.dumps(payload).encode()
            if fragment == "leaguedefaults":
                payload = json.loads(body)
                # A projection that scores zero must not replace real points.
                payload["players"].append(
                    {
                        "id": 888888,
                        "player": {
                            "id": 888888,
                            "fullName": "Christian McCaffrey",
                            "defaultPositionId": 2,
                            "stats": [
                                {
                                    "statSourceId": 1,
                                    "statSplitTypeId": 0,
                                    "seasonId": 2099,
                                    "stats": {},
                                    "appliedTotal": 0,
                                }
                            ],
                        },
                    }
                )
                body = json.dumps(payload).encode()
            return RawPayload(body=body, content_type=content_type)
        raise AssertionError(f"no fixture for {spec.url}")

    by_name = build(tmp_path, fetch)
    assert "Nobody Atall" not in by_name
    assert by_name["Christian McCaffrey"].points > 0
