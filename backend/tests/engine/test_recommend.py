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


def test_faller_is_flagged_as_value():
    out = rec([cand("x", "WR", 20, adp=40.0)], current_pick=20)
    assert any("falling" in r and "ADP 40" in r for r in out[0].reasons)


def test_reach_is_flagged_and_penalised():
    faller = rec([cand("x", "WR", 20, adp=40.0)], current_pick=20)[0]
    reacher = rec([cand("x", "WR", 20, adp=5.0)], current_pick=20)[0]
    assert reacher.score < faller.score
    assert any("a reach" in r for r in reacher.reasons)


def test_adp_value_is_capped():
    # Fill the WR slots so the need bonus doesn't muddy the comparison.
    filled = {"WR": 5}
    at_cap = rec([cand("x", "WR", 0, adp=40.0)], my_counts=filled, current_pick=20)[0]
    absurd = rec([cand("x", "WR", 0, adp=400.0)], my_counts=filled, current_pick=20)[0]
    assert absurd.score == at_cap.score == 12.0  # both pinned at the cap
    # A smaller fall earns a proportional, sub-cap bonus.
    small = rec([cand("x", "WR", 0, adp=30.0)], my_counts=filled, current_pick=20)[0]
    assert 0 < small.score < 12.0


def test_tier_about_to_empty_is_urgent():
    # Two players left in RB tier 2 and 5 picks until my turn -> urgent.
    scarce = rec(
        [cand("a", "RB", 20, tier=2), cand("b", "RB", 19, tier=2)],
        picks_until_turn=5,
    )[0]
    assert any("left in RB tier 2" in r for r in scarce.reasons)

    # A deep tier is not urgent.
    deep = rec([cand(str(i), "RB", 20, tier=2) for i in range(10)], picks_until_turn=2)[0]
    assert not any("left in RB tier" in r for r in deep.reasons)


def test_no_tier_urgency_when_on_the_clock():
    # picks_until_turn == 0 means I'm picking right now; nothing can be sniped.
    out = rec([cand("a", "RB", 20, tier=1)], picks_until_turn=0)[0]
    assert not any("tier" in r for r in out.reasons)


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
