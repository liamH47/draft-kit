from draftkit.engine.recommend import Candidate, recommend
from draftkit.models.league import LeagueConfig, RosterSlots, ScoringSettings


def league(**roster_kwargs) -> LeagueConfig:
    return LeagueConfig(
        scoring=ScoringSettings.preset("half_ppr"),
        roster=RosterSlots(**roster_kwargs),
        num_teams=12,
    )


def cand(pid, pos, vorp, **kw) -> Candidate:
    return Candidate(
        player_id=pid, name=f"Player {pid}", position=pos, points=200.0, vorp=vorp, **kw
    )


def rec(available, *, my_counts=None, current_pick=10, picks_until_turn=5, **kw):
    return recommend(
        available,
        league=league(),
        my_counts=my_counts or {},
        current_pick=current_pick,
        picks_until_turn=picks_until_turn,
        **kw,
    )


def test_autodraft_count_is_ignored_without_teams():
    """Guard the divide: a malformed league must not blow up the panel."""
    out = recommend(
        [cand("a", "RB", 20, tier=1)],
        league=league(),
        my_counts={},
        current_pick=1,
        picks_until_turn=None,
        autodraft_count=4,
    )
    assert out[0].player_id == "a"


def test_ranks_by_vorp_when_all_else_equal():
    out = rec([cand("a", "RB", 10), cand("b", "RB", 40), cand("c", "RB", 25)])
    assert [r.player_id for r in out] == ["b", "c", "a"]
    assert out[0].reasons[0].startswith("+40 pts over a replacement RB")


def test_limit_is_respected():
    assert len(rec([cand(str(i), "WR", i) for i in range(20)], limit=3)) == 3


def test_roster_need_breaks_a_vorp_tie():
    # Same VORP, but my RB slots are empty and my TE slot is filled.
    out = rec([cand("rb", "RB", 30), cand("te", "TE", 30)], my_counts={"TE": 1})
    assert out[0].player_id == "rb"
    assert any("you still need RB starters" in r for r in out[0].reasons)


def test_need_bonus_disappears_once_slots_are_filled():
    full = rec([cand("te", "TE", 30)], my_counts={"TE": 5})[0]
    assert not any("still need" in r for r in full.reasons)


def test_single_slot_need_is_half_a_two_slot_need():
    # Needing your one QB must not outbid needing two RB starters: need is
    # measured in unfilled slots (capped at two), not fraction of position.
    qb = rec([cand("qb", "QB", 20)], my_counts={})[0]
    rb = rec([cand("rb", "RB", 20)], my_counts={})[0]
    assert qb.score < rb.score


def test_flex_need_is_named_flex_not_a_contradiction():
    # Dedicated RB slots full, but the flex share keeps need > 0. The reason
    # must say "flex", never the self-contradictory "(2/2 filled)".
    out = rec([cand("rb", "RB", 30)], my_counts={"RB": 2})
    assert any("flex is still open" in r for r in out[0].reasons)
    assert not any("still need" in r for r in out[0].reasons)


def test_faller_is_flagged_as_value():
    # ADP 5 still on the board at pick 20: he has fallen 15 picks.
    out = rec([cand("x", "WR", 20, adp=5.0)], current_pick=20)
    assert any("falling" in r and "ADP 5" in r for r in out[0].reasons)


def test_reach_is_flagged_and_penalised():
    faller = rec([cand("x", "WR", 20, adp=5.0)], current_pick=20)[0]
    reacher = rec([cand("x", "WR", 20, adp=40.0)], current_pick=20)[0]
    assert reacher.score < faller.score
    assert any("a reach" in r for r in reacher.reasons)


def test_adp_value_is_capped():
    # Fill the WR slots so the need bonus doesn't muddy the comparison.
    filled = {"WR": 5}
    at_cap = rec([cand("x", "WR", 0, adp=20.0)], my_counts=filled, current_pick=40)[0]
    absurd = rec([cand("x", "WR", 0, adp=1.0)], my_counts=filled, current_pick=40)[0]
    assert absurd.score == at_cap.score == 12.0  # both pinned at the cap
    # A smaller fall earns a proportional, sub-cap bonus.
    small = rec([cand("x", "WR", 0, adp=30.0)], my_counts=filled, current_pick=40)[0]
    assert 0 < small.score < 12.0


def test_reaches_keep_hurting_past_the_value_cap():
    # A 3-round reach must cost real points, not the same -12 as a 20-pick one
    # — that symmetry was how an ADP-127 TE topped the board at pick 79.
    filled = {"WR": 5}
    reach_20 = rec([cand("x", "WR", 0, adp=60.0)], my_counts=filled, current_pick=40)[0]
    reach_48 = rec([cand("x", "WR", 0, adp=88.0)], my_counts=filled, current_pick=40)[0]
    assert reach_48.score < reach_20.score
    # ...but the reach side saturates too, eventually.
    reach_absurd = rec([cand("x", "WR", 0, adp=300.0)], my_counts=filled, current_pick=40)[0]
    assert reach_absurd.score == -30.0


def test_a_position_about_to_fall_off_is_urgent():
    """The whole point of scarcity: a real drop behind him is worth paying
    for, and a position that keeps is not."""
    steep = rec([cand("a", "RB", 40, vona=30.0)])[0]
    flat = rec([cand("a", "RB", 40, vona=1.0)])[0]
    assert steep.score > flat.score
    assert any("waiting costs" in r for r in steep.reasons)


def test_a_position_that_keeps_says_so():
    out = rec([cand("a", "RB", 40, vona=1.0)], picks_until_turn=10)[0]
    assert any("RB keeps" in r for r in out.reasons)


def test_scarcity_is_absent_when_it_cannot_be_measured():
    """No next pick (the final round) means nothing to wait for."""
    out = rec([cand("a", "RB", 20)])[0]
    assert out.vona is None
    assert not any("waiting costs" in r or "keeps" in r for r in out.reasons)


def test_target_tag_lifts_a_player_over_a_better_one():
    plain = cand("better", "RB", 30)
    tagged = cand("mine", "RB", 20, tag="target")
    out = rec([plain, tagged])
    assert out[0].player_id == "mine"
    assert "you tagged him a target" in out[0].reasons


def test_fade_tag_buries_a_player():
    out = rec([cand("fade", "RB", 40, tag="fade"), cand("plain", "RB", 20)])
    assert out[0].player_id == "plain"
    assert any("fade" in r for r in out[-1].reasons)


def test_at_adp_tag_is_neutral():
    tagged = rec([cand("x", "RB", 20, tag="at_adp")])[0]
    untagged = rec([cand("x", "RB", 20)])[0]
    assert tagged.score == untagged.score


def test_empty_pool_returns_nothing():
    assert rec([]) == []


# --- list vs market: the smallest term, and the only one about other people --


def test_list_followers_reaching_is_flagged():
    """Positive list_vs_market (ADP - rank) means the lists have him above his
    market price, so autodrafters and anyone on the default order take him
    early."""
    out = rec([cand("x", "WR", 20, list_vs_market=20.0)])
    assert any("list-followers reach for him" in r for r in out[0].reasons)


def test_a_player_the_lists_are_cold_on_is_flagged():
    out = rec([cand("x", "WR", 20, list_vs_market=-20.0)])
    assert any("the lists are cold on him" in r for r in out[0].reasons)


def test_small_list_disagreements_stay_quiet():
    out = rec([cand("x", "WR", 20, list_vs_market=4.0)])
    assert not any("list" in r for r in out[0].reasons)


def test_the_list_nudge_cannot_outweigh_real_value():
    """It predicts behaviour, not value, so it must never decide a pick."""
    better = cand("better", "RB", 30)
    nudged = cand("nudged", "RB", 20, list_vs_market=200.0)  # absurd, still capped
    out = rec([better, nudged])
    assert out[0].player_id == "better"


def test_no_list_data_is_simply_no_term():
    with_list = rec([cand("x", "RB", 20, list_vs_market=0.0)])[0]
    without = rec([cand("x", "RB", 20)])[0]
    assert with_list.score == without.score


# --- must-fill: the endgame cannot skip a mandatory slot --------------------


def test_must_fill_forces_the_last_open_slot():
    # Final pick, only K unfilled: the kicker outranks a higher-vorp bench body
    # who would never start.
    my = {"QB": 1, "RB": 5, "WR": 5, "TE": 2, "DEF": 1}
    out = rec(
        [cand("qb2", "QB", 25), cand("k", "K", 0)],
        my_counts=my,
        current_round=15,
        total_rounds=15,
    )
    assert out[0].player_id == "k"
    assert any("must fill K" in r for r in out[0].reasons)


def test_must_fill_stays_quiet_while_there_is_slack():
    out = rec(
        [cand("k", "K", 0), cand("rb", "RB", 30)],
        my_counts={},
        current_round=1,
        total_rounds=15,
    )
    assert out[0].player_id == "rb"
    assert not any("must fill" in r for rec_ in out for r in rec_.reasons)


def test_must_fill_overrides_the_late_round_hold():
    # Round 11 of 15: five picks left and five dedicated slots empty, so the
    # K/DEF hold must not bury the positions the roster now depends on.
    my = {"RB": 2, "WR": 1}
    out = rec(
        [cand("k", "K", 0), cand("rb", "RB", 30)],
        my_counts=my,
        current_round=11,
        total_rounds=15,
    )
    k = next(r for r in out if r.player_id == "k")
    assert not any("wait on K" in r for r in k.reasons)
    assert out[0].player_id == "k"


def test_no_must_fill_once_the_lineup_is_full():
    my = {"QB": 1, "RB": 5, "WR": 5, "TE": 2, "K": 1, "DEF": 1}
    out = rec([cand("rb", "RB", 30)], my_counts=my, current_round=15, total_rounds=15)
    assert not any("must fill" in r for r in out[0].reasons)


# --- autodrafters -----------------------------------------------------------


def test_autodrafters_damp_scarcity():
    """Half the room on autopilot cannot start a run, so a position drains
    more slowly even though the pick count is unchanged."""
    field = [cand("a", "RB", 20, vona=20.0)]
    humans = rec(field, picks_until_turn=8, autodraft_count=0)[0]
    robots = rec(field, picks_until_turn=8, autodraft_count=6)[0]
    assert robots.score < humans.score


def test_a_fully_automated_room_creates_no_urgency():
    out = rec([cand("a", "RB", 20, vona=20.0)], picks_until_turn=8, autodraft_count=12)[0]
    assert not any("waiting costs" in r for r in out.reasons)
