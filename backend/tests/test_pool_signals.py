"""The signals added on 2026-08-23: a fifth market, buzz, and injury.

Two of these come from data we were already downloading and discarding, and
the third is a market whose join key the crosswalk already carried. None of
them may cost the pool if the source is missing — that rule is the point of
the whole snapshot design.
"""

import json

import pytest

from draftkit.models.league import DEFAULT_ADP_WEIGHTS, LeagueConfig, ScoringSettings
from draftkit.pool import build_pool
from draftkit.snapshots.store import SnapshotStore
from draftkit.sources.base import RawPayload
from tests.conftest import _URL_TO_FIXTURE

LEAGUE = LeagueConfig(scoring=ScoringSettings.preset("half_ppr"))


def build(tmp_path, fetcher, **kwargs):
    result = build_pool(
        SnapshotStore(tmp_path, fetcher), LEAGUE, season=2026, scoring_preset="half_ppr", **kwargs
    )
    return {p.name: p for p in result.players}


def rewriting_fetcher(rewrite):
    """A fetcher that serves the recorded fixtures, letting a test rewrite one
    payload (or raise, to take a source away entirely)."""

    def fetch(spec):
        for fragment, path, content_type in _URL_TO_FIXTURE:
            if fragment in spec.url:
                body = rewrite(fragment, path.read_bytes())
                return RawPayload(body=body, content_type=content_type)
        raise AssertionError(f"no fixture for {spec.url}")

    return fetch


# --- MyFantasyLeague, the fifth market --------------------------------------


def test_mfl_joins_on_the_crosswalks_own_primary_key(tmp_path, fixture_fetcher):
    by_name = build(tmp_path, fixture_fetcher)
    cmc = by_name["Christian McCaffrey"]
    assert "mfl" in cmc.adp_by_source
    assert cmc.adp_by_source["mfl"] > 0


def test_losing_mfl_costs_its_column_and_nothing_else(tmp_path):
    def rewrite(fragment, body):
        if fragment == "myfantasyleague":
            raise ConnectionError("MFL down")
        return body

    by_name = build(tmp_path, rewriting_fetcher(rewrite))
    cmc = by_name["Christian McCaffrey"]
    assert "mfl" not in cmc.adp_by_source
    assert cmc.adp is not None  # the other markets still price the board


def test_a_market_added_later_cannot_outweigh_the_others_by_default():
    """blend_adp gives an unlisted source weight 1.0, so a league saved before
    MFL existed would have counted it double against every other market. The
    defaults are filled in before blending; this is the guard on that."""
    saved_before_mfl = LeagueConfig(
        scoring=ScoringSettings.preset("half_ppr"),
        adp_weights={"sleeper": 0.5, "ffcalc": 0.5, "espn": 0.5, "yahoo": 0.5},
    )
    assert "mfl" not in saved_before_mfl.adp_weights
    filled = {**DEFAULT_ADP_WEIGHTS, **saved_before_mfl.adp_weights}
    assert filled["mfl"] == filled["ffcalc"] == 0.5


def test_a_league_can_still_override_a_market_weight():
    league = LeagueConfig(scoring=ScoringSettings.preset("ppr"), adp_weights={"mfl": 2.0})
    filled = {**DEFAULT_ADP_WEIGHTS, **league.adp_weights}
    assert filled["mfl"] == 2.0
    assert filled["ffcalc"] == 0.5  # the rest keep their defaults


# --- buzz --------------------------------------------------------------------


def _trending(pairs):
    return json.dumps([{"player_id": pid, "count": n} for pid, n in pairs]).encode()


def test_buzz_scales_against_the_hottest_add_in_the_window(tmp_path):
    """Raw counts depend on how many people happened to be on Sleeper today and
    mean nothing on their own, so the column is relative to the peak."""

    def rewrite(fragment, body):
        if fragment == "trending/add":
            return _trending([("4034", 1000), ("9221", 250)])  # McCaffrey, Gibbs
        if fragment == "trending/drop":
            return _trending([("9509", 500)])
        return body

    by_name = build(tmp_path, rewriting_fetcher(rewrite))
    assert by_name["Christian McCaffrey"].buzz == 100
    assert by_name["Jahmyr Gibbs"].buzz == 25


def test_a_player_the_rooms_are_dropping_reads_negative(tmp_path):
    def rewrite(fragment, body):
        if fragment == "trending/add":
            return _trending([("4034", 1000)])
        if fragment == "trending/drop":
            return _trending([("9221", 400)])  # Gibbs, being dropped
        return body

    by_name = build(tmp_path, rewriting_fetcher(rewrite))
    assert by_name["Jahmyr Gibbs"].buzz == -40


def test_a_player_nobody_is_moving_has_no_buzz_at_all(tmp_path):
    """None, not zero: "nobody touched him" and "he is exactly average" are
    different claims, and only one of them is true."""

    def rewrite(fragment, body):
        if fragment == "trending/add":
            return _trending([("4034", 1000)])
        if fragment == "trending/drop":
            return _trending([("4034", 10)])
        return body

    by_name = build(tmp_path, rewriting_fetcher(rewrite))
    assert by_name["Jahmyr Gibbs"].buzz is None


def test_losing_the_trending_feed_costs_the_column_and_nothing_else(tmp_path):
    def rewrite(fragment, body):
        if fragment.startswith("trending/"):
            raise ConnectionError("trending down")
        return body

    by_name = build(tmp_path, rewriting_fetcher(rewrite))
    assert all(p.buzz is None for p in by_name.values())
    assert by_name["Christian McCaffrey"].value > 0


def test_a_window_where_every_player_was_dropped_has_no_peak_to_scale_by(tmp_path):
    """Degenerate but reachable: divide-by-zero territory if the peak is not
    checked before it is used."""

    def rewrite(fragment, body):
        if fragment == "trending/add":
            return _trending([("4034", 1)])
        if fragment == "trending/drop":
            return _trending([("4034", 50)])
        return body

    by_name = build(tmp_path, rewriting_fetcher(rewrite))
    assert by_name["Christian McCaffrey"].buzz is None


# --- injury ------------------------------------------------------------------


def test_injury_and_depth_chart_reach_the_pool(tmp_path):
    def rewrite(fragment, body):
        if fragment == "players/nfl":
            payload = json.loads(body)
            payload["4034"] |= {
                "injury_status": "IR",
                "injury_body_part": "Knee - ACL",
                "depth_chart_order": 1,
            }
            return json.dumps(payload).encode()
        return body

    by_name = build(tmp_path, rewriting_fetcher(rewrite))
    cmc = by_name["Christian McCaffrey"]
    assert cmc.injury_status == "IR"
    assert cmc.injury_body_part == "Knee - ACL"
    assert cmc.depth_chart_order == 1
    assert by_name["Jahmyr Gibbs"].injury_status is None


# --- the user's own lists ----------------------------------------------------


def test_a_custom_list_joins_the_published_ones(tmp_path, fixture_fetcher):
    plain = build(tmp_path, fixture_fetcher)
    with_list = build(tmp_path, fixture_fetcher, custom_ranks={"mine": {"4034": 1.0}})
    cmc = with_list["Christian McCaffrey"]
    assert cmc.rank_by_source["custom:mine"] == 1.0
    assert cmc.consensus_rank != plain["Christian McCaffrey"].consensus_rank


def test_a_custom_list_is_namespaced_so_it_cannot_shadow_a_feed(tmp_path, fixture_fetcher):
    """A list the user calls "espn" must not quietly replace ESPN's own."""
    by_name = build(tmp_path, fixture_fetcher, custom_ranks={"espn": {"4034": 99.0}})
    ranks = by_name["Christian McCaffrey"].rank_by_source
    assert ranks["custom:espn"] == 99.0
    assert ranks["espn"] != 99.0


@pytest.mark.parametrize("custom", [None, {}])
def test_no_custom_lists_changes_nothing(tmp_path, fixture_fetcher, custom):
    by_name = build(tmp_path, fixture_fetcher, custom_ranks=custom)
    assert not any(
        key.startswith("custom:") for key in by_name["Christian McCaffrey"].rank_by_source
    )


def test_a_list_where_nothing_resolved_contributes_no_column(tmp_path):
    """A cheat sheet whose names all failed to match must not put an empty
    source on every player. The rows stay in the table so the user can see
    what went wrong; the pool simply has nothing to join."""
    from draftkit.db import repo
    from draftkit.db.connection import connect, migrate

    conn = connect(tmp_path / "app.db")
    migrate(conn)
    repo.replace_ranking_list(
        conn,
        "all-misses",
        [{"rank": 1, "player_id": None, "source_name": "Nobody At All"}],
        user_id="local",
    )
    repo.replace_ranking_list(
        conn, "one-hit", [{"rank": 1, "player_id": "4034", "source_name": "x"}], user_id="local"
    )
    assert repo.custom_ranks_for_pool(conn, "local") == {"one-hit": {"4034": 1.0}}
    conn.close()


def test_the_cache_notices_a_list_that_changed(tmp_path, fixture_fetcher):
    """The pool is cached per configuration and a pasted list is part of that
    configuration. Without the list in the cache key, a freshly imported cheat
    sheet would not appear until the cache lapsed — five minutes into a draft."""
    from draftkit.pool import build_pool_cached

    store = SnapshotStore(tmp_path, fixture_fetcher)

    def cached(custom):
        result = build_pool_cached(
            store, LEAGUE, season=2026, scoring_preset="half_ppr", custom_ranks=custom
        )
        return {p.name: p for p in result.players}

    first = cached({"mine": {"4034": 1.0}})
    assert first["Christian McCaffrey"].rank_by_source["custom:mine"] == 1.0
    again = cached({"mine": {"4034": 1.0}})
    assert again["Christian McCaffrey"].rank_by_source["custom:mine"] == 1.0
    changed = cached({"mine": {"4034": 40.0}})
    assert changed["Christian McCaffrey"].rank_by_source["custom:mine"] == 40.0
