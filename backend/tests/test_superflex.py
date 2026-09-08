"""Superflex is a different market, not a scoring tweak.

A second quarterback slot reprices the position violently — the consensus has
Josh Allen 1st on its superflex board and 28th on its one-QB board of the same
date, and Sleeper's own two-QB ADP has him at 3.4 against 20.9 in half-PPR.
Every published source here answers one question or the other, never both, so
the league's ROSTER decides which of them the pool is allowed to read.

Getting this wrong is not a rounding error. Fed one-QB prices, the board
charged a thirty-point reach penalty to anyone taking a quarterback at his
real superflex price, and its survival model — the thing that decides wait
cost — concluded every quarterback would still be sitting there next turn.
"""

from draftkit.engine.adp import ONE_QB_ONLY_LISTS, format_ranks
from draftkit.models.league import LeagueConfig, RosterSlots, ScoringSettings
from draftkit.pool import build_pool
from draftkit.snapshots.store import SnapshotStore
from draftkit.sources import ffcalc_adp, sleeper_projections
from draftkit.sources.base import RawPayload
from tests.conftest import _URL_TO_FIXTURE


def league(superflex: int) -> LeagueConfig:
    return LeagueConfig(
        scoring=ScoringSettings.preset("half_ppr"),
        roster=RosterSlots(superflex=superflex),
        num_teams=10,
    )


def build(tmp_path, fetcher, superflex: int):
    result = build_pool(
        SnapshotStore(tmp_path, fetcher),
        league(superflex),
        season=2026,
        scoring_preset="half_ppr",
    )
    return {p.name: p for p in result.players}


# --- which lists are allowed to form a consensus ----------------------------


def test_one_qb_lists_are_dropped_from_a_superflex_consensus():
    ranks = {"espn": 19.0, "cbs": 20.0, "expert": 25.0, "fantasypros": 1.0, "custom:mine": 2.0}
    assert format_ranks(ranks, superflex=True) == {"fantasypros": 1.0, "custom:mine": 2.0}


def test_every_list_counts_in_a_one_qb_league():
    """The filter must be inert outside superflex — this is the common case."""
    ranks = {"espn": 19.0, "fantasypros": 22.0}
    assert format_ranks(ranks, superflex=False) == ranks


def test_the_dropped_lists_are_the_ones_with_no_superflex_board():
    """Named rather than assumed: FantasyPros is the only source here that
    publishes a superflex order, so it is the only one that may survive."""
    assert set(ONE_QB_ONLY_LISTS) == {"espn", "cbs", "expert"}
    assert "fantasypros" not in ONE_QB_ONLY_LISTS


# --- which markets the pool actually reads ----------------------------------


def test_superflex_asks_each_source_for_its_two_qb_list(tmp_path):
    seen: list[str] = []

    def fetch(spec):
        seen.append(spec.url)
        for fragment, path, content_type in _URL_TO_FIXTURE:
            if fragment in spec.url:
                return RawPayload(body=path.read_bytes(), content_type=content_type)
        raise AssertionError(f"no fixture for {spec.url}")

    build(tmp_path, fetch, superflex=1)
    ffc = [u for u in seen if "fantasyfootballcalculator" in u]
    assert ffc and all("/2qb?" in u for u in ffc), ffc
    assert any("superflex" in u for u in seen if "fantasypros" in u)


def test_sleeper_and_ffc_both_publish_the_two_qb_market():
    """The fix depends on these existing; if either adapter drops the format
    the pool would silently fall back to a one-QB price."""
    assert "adp_2qb" in sleeper_projections.ADP_FIELDS
    assert "2qb" in ffcalc_adp.FORMATS
    assert "/2qb?" in ffcalc_adp.request({"format": "2qb", "year": 2026}).url


def test_markets_with_no_superflex_variant_are_dropped_not_blended(tmp_path, fixture_fetcher):
    """ESPN, Yahoo and MFL price one-QB drafts. Averaging them with a real
    superflex market does not make the answer noisier, it makes it wrong —
    three votes for the wrong game against two for the right one."""
    superflex = build(tmp_path, fixture_fetcher, superflex=1)
    one_qb = build(tmp_path / "b", fixture_fetcher, superflex=0)

    priced = [p for p in superflex.values() if p.adp_by_source]
    assert priced, "the superflex pool must still carry prices"
    for player in priced:
        assert not {"espn", "yahoo", "mfl"} & set(player.adp_by_source)

    # ...and those same markets are present when the format matches them.
    assert any({"espn", "yahoo", "mfl"} & set(p.adp_by_source) for p in one_qb.values())
