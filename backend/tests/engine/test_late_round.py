"""Kickers and defenses wait until the end of the draft.

Taking a kicker in round 6 costs a starter you can't get back, and K1 vs K12
is worth a fraction of what RB1 vs RB12 is worth. The engine holds them back
until the tail of the draft, with three deliberate escape hatches.
"""

from draftkit.engine.recommend import Candidate, recommend
from draftkit.models.league import LeagueConfig, RosterSlots, ScoringSettings


def league(**kwargs) -> LeagueConfig:
    return LeagueConfig(
        scoring=ScoringSettings.preset("half_ppr"),
        roster=RosterSlots(**kwargs.pop("roster", {})),
        num_teams=12,
        **kwargs,
    )


def cand(pid, pos, vorp, **kw) -> Candidate:
    return Candidate(
        player_id=pid, name=f"Player {pid}", position=pos, points=120.0, vorp=vorp, **kw
    )


def rec(available, *, cfg=None, my_counts=None, current_round=1, total_rounds=15, **kw):
    return recommend(
        available,
        league=cfg or league(),
        my_counts=my_counts or {},
        current_pick=kw.pop("current_pick", 10),
        current_round=current_round,
        total_rounds=total_rounds,
        **kw,
    )


FIELD = [cand("rb", "RB", 8), cand("k", "K", 20), cand("dst", "DEF", 18)]


def test_kicker_and_defense_sink_early_despite_better_vorp():
    out = rec(FIELD, current_round=3)
    assert out[0].player_id == "rb"  # the 8-VORP back beats a 20-VORP kicker
    held = {r.player_id: r for r in out}
    assert "wait on K — round 13 or later is the spot" in held["k"].reasons
    assert "wait on DEF — round 13 or later is the spot" in held["dst"].reasons
    assert held["k"].score < 0


def test_they_score_normally_inside_the_late_window():
    out = rec(FIELD, current_round=13)
    assert out[0].player_id == "k"  # highest VORP wins again
    assert not any("wait on" in reason for r in out for reason in r.reasons)


def held_back(out) -> bool:
    return any("wait on" in reason for r in out for reason in r.reasons)


# A plausible late-middle-rounds roster that keeps the hold in play: an empty
# roster there would (correctly) trip the must-fill override, and a complete
# skill lineup would (correctly) declare starters set — TE stays open.
MID_DRAFT = {"QB": 1, "RB": 3, "WR": 3, "TE": 0}


def test_window_boundary_is_exact():
    # 15 rounds with a window of 3: rounds 13-15 are fair game, round 12 is not.
    assert held_back(rec(FIELD, my_counts=MID_DRAFT, current_round=12))
    assert not held_back(rec(FIELD, my_counts=MID_DRAFT, current_round=13))


def test_no_tier_urgency_or_need_bonus_while_held_back():
    """A lone scarce kicker must not manufacture urgency in round 2."""
    out = rec([cand("k", "K", 5, vona=30.0)], current_round=2)
    reasons = out[0].reasons
    assert not any("left in K tier" in r for r in reasons)
    assert not any("still need K starters" in r for r in reasons)


def test_escape_hatch_roster_otherwise_set():
    # Every real starting slot filled: 1 QB, 2 RB, 2 WR, 1 TE (+1 flex spread).
    full = {"QB": 1, "RB": 3, "WR": 3, "TE": 2}
    out = rec(FIELD, my_counts=full, current_round=5)
    kicker = next(r for r in out if r.player_id == "k")
    assert "your starters are set, so this is a fine time" in kicker.reasons
    assert kicker.score > 0


def test_starters_set_counts_flex_by_surplus():
    # 7 skill slots (1QB/2RB/2WR/1TE + flex) filled by exactly 7 players. The
    # old fractional check demanded 3RB+3WR+2TE = 9 before conceding, firing
    # two rounds late.
    seven = {"QB": 1, "RB": 3, "WR": 2, "TE": 1}
    out = rec(FIELD, my_counts=seven, current_round=8)
    kicker = next(r for r in out if r.player_id == "k")
    assert "your starters are set, so this is a fine time" in kicker.reasons

    # Surplus at one position cannot cover a dedicated slot at another.
    lopsided = {"QB": 1, "RB": 4, "WR": 1, "TE": 1}
    held = rec(FIELD, my_counts=lopsided, current_round=8)
    assert any("wait on K" in r for rec_ in held for r in rec_.reasons)


def test_escape_hatch_elite_outlier():
    out = rec([cand("k", "K", 40)], current_round=4)
    assert "unusually big edge at K for this stage" in out[0].reasons
    assert out[0].score > 0


def test_an_ordinary_kicker_is_not_an_outlier():
    out = rec([cand("k", "K", 24)], current_round=4)  # just under the threshold
    assert any("wait on K" in r for r in out[0].reasons)


def test_held_positions_keep_their_order_relative_to_each_other():
    out = rec([cand("k1", "K", 12), cand("k2", "K", 4)], current_round=2)
    assert [r.player_id for r in out] == ["k1", "k2"]


def test_the_hold_is_configurable():
    cfg = league(late_round_positions=["K"], late_round_window=5)
    # DEF is no longer held at all; K is fair game from round 11 with window 5.
    assert not held_back(rec(FIELD, cfg=cfg, my_counts=MID_DRAFT, current_round=11))

    early = rec(FIELD, cfg=cfg, my_counts=MID_DRAFT, current_round=9)
    assert any("wait on K" in reason for r in early for reason in r.reasons)
    assert not any("wait on DEF" in reason for r in early for reason in r.reasons)


def test_disabling_the_hold_entirely():
    cfg = league(late_round_positions=[])
    out = rec(FIELD, cfg=cfg, current_round=1)
    assert out[0].player_id == "k"
