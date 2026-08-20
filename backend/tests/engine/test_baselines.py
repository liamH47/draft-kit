from draftkit.engine.baselines import (
    baselines,
    drafted_by_position,
    starters_by_position,
)
from draftkit.models.league import LeagueConfig, RosterSlots, ScoringSettings


def league(**roster_kwargs) -> LeagueConfig:
    return LeagueConfig(
        scoring=ScoringSettings.preset("half_ppr"),
        roster=RosterSlots(**roster_kwargs),
        num_teams=12,
    )


def test_flex_is_spread_over_eligible_positions():
    starters = starters_by_position(RosterSlots(qb=1, rb=2, wr=2, te=1, flex=1, k=1, dst=1))
    assert starters["QB"] == 1  # QB is not flex-eligible
    assert starters["K"] == 1
    # One flex split across 5 dedicated RB/WR/TE slots, by share.
    assert starters["RB"] == 2 + 2 / 5
    assert starters["WR"] == 2 + 2 / 5
    assert starters["TE"] == 1 + 1 / 5
    assert round(sum(starters[p] for p in ("RB", "WR", "TE")), 6) == 6.0


def test_superflex_goes_to_quarterback():
    single = starters_by_position(RosterSlots(superflex=0))
    superflex = starters_by_position(RosterSlots(superflex=1))
    assert superflex["QB"] == single["QB"] + 1
    assert superflex["RB"] == single["RB"]


def test_bench_depth_skips_kickers_and_defenses():
    roster = RosterSlots(bench=6)
    starters = starters_by_position(roster)
    depth = drafted_by_position(roster)
    assert depth["K"] == starters["K"]
    assert depth["DEF"] == starters["DEF"]
    assert depth["RB"] > starters["RB"]
    # Six bench spots are distributed, not invented.
    assert round(sum(depth.values()) - sum(starters.values()), 6) == 6.0


def test_baselines_pick_the_right_players():
    # 12 teams, 1 QB, no flex/bench: the 12th QB is the last starter, so the
    # VOLS baseline is QB13 -- index 12 in a 0-based list.
    cfg = league(qb=1, rb=0, wr=0, te=0, flex=0, k=0, dst=0, bench=0)
    qb_points = [400.0 - i * 10 for i in range(30)]  # QB1=400, QB13=280
    result = baselines(cfg, {"QB": qb_points})
    assert result["QB"]["vols"] == 280
    assert result["QB"]["vorp"] == 280  # no bench => same baseline


def test_superflex_raises_the_qb_baseline():
    points = {"QB": [400.0 - i * 10 for i in range(40)]}
    single = baselines(league(qb=1, bench=0, flex=0), points)["QB"]["vols"]
    superflex = baselines(league(qb=1, superflex=1, bench=0, flex=0), points)["QB"]["vols"]
    # Twice as many QBs start, so replacement level is much deeper and every
    # startable QB is worth correspondingly more.
    assert superflex < single


def test_baseline_clamps_when_the_pool_is_short():
    cfg = league()
    result = baselines(cfg, {"TE": [100.0, 90.0]})
    assert result["TE"]["vols"] == 90.0  # falls back to the worst known player
    assert baselines(cfg, {"TE": []})["TE"]["vols"] == 0.0
