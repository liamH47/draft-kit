"""Ranked pick recommendations, with the reasoning shown.

A number nobody understands is a number nobody trusts mid-draft, so every
candidate carries the plain-English reasons behind its score. The score is a
sum of interpretable parts:

  VORP              — the backbone: value over a replacement-level player
  roster need       — unfilled starting slots, decaying as they fill
  ADP value         — is he falling past his market price, or a reach?
  scarcity (VONA)   — what waiting costs: how much better he is than the man
                      who will still be there at my next pick
  list vs market    — a small nudge: where the room's own list disagrees with
                      the market, weighted down because it predicts behaviour
                      rather than measuring value
  late-round hold   — kickers and defenses wait until the end of the draft
  must-fill         — when every remaining pick is needed for an empty starting
                      slot, those positions outrank everything
  your own tags     — target / at-ADP / fade override the market entirely

All pure functions over plain data: no I/O, no database, no clock.
"""

from dataclasses import dataclass, field

from draftkit.engine.baselines import starters_by_position

# Tunables. Units are fantasy points, so they're comparable to VORP directly.
NEED_BONUS = 18.0  # a fully unfilled starting slot is worth this much
ADP_VALUE_PER_PICK = 0.6  # points per pick a player has fallen past his ADP
ADP_VALUE_CAP = 12.0  # ...but a 40-pick faller isn't 40 picks better
# The reach side saturates much later: capping both at 12 made a 48-pick reach
# cost the same as a 20-pick one, which is how a TE going three rounds early
# still topped the board once the need bonus liked his position.
ADP_REACH_CAP = 30.0
# Scarcity, priced as VONA: how much better he is than the best player at his
# position likely to survive to my next pick. Replaces a tier-count rule that
# fired for nearly every tiered player at a full snake gap, which made it a
# constant rather than a signal. This one is zero when the position keeps.
SCARCITY_PER_POINT = 0.5
SCARCITY_CAP = 16.0
TAG_POINTS = {"target": 22.0, "at_adp": 0.0, "fade": -30.0}
# Enough to bury a kicker beneath any real contributor without scrambling the
# ordering among kickers themselves.
LATE_ROUND_PENALTY = 60.0
# An empty starting slot scores zero every week, so when the remaining picks
# are exactly spoken for, filling them dominates any candidate's upside.
MUST_FILL_BONUS = 100.0
# ...unless he is a genuine outlier at the position. Kickers and defenses
# cluster tightly, so clearing this much over replacement is rare and real.
LATE_ROUND_ELITE_VORP = 25.0
# Deliberately the smallest term in the model. A ranking list predicts who gets
# taken, not who is good, and the projections already answer the second
# question — so this breaks ties and never decides a pick on its own.
LIST_VALUE_PER_PICK = 0.15
LIST_VALUE_CAP = 5.0


@dataclass
class Candidate:
    player_id: str
    name: str
    position: str
    points: float
    vorp: float
    adp: float | None = None
    tier: int | None = None
    tag: str | None = None
    # Positive when ranking lists sit above the market on him: list-followers
    # (autodrafters, anyone drafting off the platform's default order) reach for
    # him sooner than the market would.
    list_vs_market: float | None = None
    # Value over the next available player at his position, measured at my
    # NEXT pick. Near zero means the position keeps and the pick is better
    # spent elsewhere; large means the drop-off behind him is real.
    vona: float | None = None


@dataclass
class Recommendation:
    player_id: str
    name: str
    position: str
    score: float
    vorp: float
    vona: float | None = None
    reasons: list[str] = field(default_factory=list)


def _need_factor(position: str, my_counts: dict[str, int], starters: dict[str, float]) -> float:
    """Need in unfilled-slot units, saturating at two slots.

    Normalizing by fraction-of-position-filled made every single-slot position
    a binary cliff: "1 of 1 QB empty" paid the same full bonus as "all WR
    slots empty", never decayed, and mid-draft that flat subsidy outbid real
    value gaps (two QBs in one top five). Counting slots instead makes needing
    your one QB half as needy as needing two WR starters — and superflex QB
    (two slots) earns the full bonus without a special case."""
    needed = starters.get(position, 0.0)
    if needed <= 0:
        return 0.0
    filled = my_counts.get(position, 0)
    return min(max(needed - filled, 0.0), 2.0) / 2.0


def _real_starters_filled(my_counts: dict[str, int], league, late_positions: list[str]) -> bool:
    """True once every starting slot outside the late-round positions is
    filled. Flex and superflex are counted by surplus at their eligible
    positions — comparing counts against fractional flex-spread quotas would
    demand a 3rd RB AND a 3rd WR AND a 2nd TE, declaring starters set two
    rounds late."""
    roster = league.roster
    dedicated = {
        "QB": roster.qb,
        "RB": roster.rb,
        "WR": roster.wr,
        "TE": roster.te,
        "K": roster.k,
        "DEF": roster.dst,
    }
    if any(
        my_counts.get(position, 0) < slots
        for position, slots in dedicated.items()
        if position not in late_positions
    ):
        return False
    skill_slots = roster.qb + roster.rb + roster.wr + roster.te + roster.flex + roster.superflex
    skill_have = sum(my_counts.get(p, 0) for p in ("QB", "RB", "WR", "TE"))
    return skill_have >= skill_slots


def recommend(
    available: list[Candidate],
    *,
    league,
    my_counts: dict[str, int],
    current_pick: int,
    picks_until_turn: int | None,
    current_round: int = 1,
    total_rounds: int = 15,
    autodraft_count: int = 0,
    limit: int = 5,
) -> list[Recommendation]:
    starters = starters_by_position(league.roster)
    late_positions = list(league.late_round_positions)

    # Autodrafters walk a ranking list; they do not panic, chase runs or reach.
    # So the pressure between now and your next turn comes only from the humans,
    # and a room that is half robots is far calmer than the raw pick count says.
    human_share = 1.0
    if autodraft_count and league.num_teams:
        human_share = max(0.0, (league.num_teams - autodraft_count) / league.num_teams)
    human_until_turn = None if picks_until_turn is None else round(picks_until_turn * human_share)
    rounds_left = total_rounds - current_round + 1
    # Inside the tail of the draft, kickers and defenses score normally.
    in_late_window = rounds_left <= league.late_round_window
    roster_otherwise_set = _real_starters_filled(my_counts, league, late_positions)
    first_late_round = max(1, total_rounds - league.late_round_window + 1)

    # Dedicated starting slots (whole numbers — flex fractions excluded) still
    # unfilled. When they need every pick I have left, nothing else can be
    # afforded: an empty slot scores zero every single week.
    dedicated = {
        "QB": league.roster.qb,
        "RB": league.roster.rb,
        "WR": league.roster.wr,
        "TE": league.roster.te,
        "K": league.roster.k,
        "DEF": league.roster.dst,
    }
    shortfall = {
        pos: slots - my_counts.get(pos, 0)
        for pos, slots in dedicated.items()
        if slots > my_counts.get(pos, 0)
    }
    must_fill = bool(shortfall) and sum(shortfall.values()) >= rounds_left

    out: list[Recommendation] = []
    for c in available:
        score = c.vorp
        reasons: list[str] = []

        forced = must_fill and c.position in shortfall
        if forced:
            score += MUST_FILL_BONUS
            reasons.append(
                f"you must fill {c.position} — every one of your "
                f"{rounds_left} remaining picks is spoken for"
            )

        # A kicker drafted in round 6 costs a starter you cannot replace, so
        # hold K and DEF back until the end — unless this is the end, your
        # lineup is otherwise complete, or he is a true outlier.
        held_back = False
        if c.position in late_positions and not in_late_window and not forced:
            elite = c.vorp >= LATE_ROUND_ELITE_VORP
            if roster_otherwise_set:
                reasons.append("your starters are set, so this is a fine time")
            elif elite:
                reasons.append(f"unusually big edge at {c.position} for this stage")
            else:
                held_back = True
                score -= LATE_ROUND_PENALTY
                reasons.append(
                    f"wait on {c.position} — round {first_late_round} or later is the spot"
                )

        if c.vorp > 0:
            reasons.append(f"{c.vorp:+.0f} pts over a replacement {c.position}")

        need = 0.0 if held_back else _need_factor(c.position, my_counts, starters)
        if need > 0:
            bonus = NEED_BONUS * need
            score += bonus
            filled = my_counts.get(c.position, 0)
            want = starters.get(c.position, 0)
            # Flex spreads fractional slots over RB/WR/TE, so a position can
            # still carry need after its dedicated slots are full — that
            # remainder is the flex, and the reason should say so.
            if filled < int(want):
                reasons.append(
                    f"you still need {c.position} starters ({filled}/{int(want)} filled)"
                )
            else:
                reasons.append("your flex is still open")

        if c.adp is not None:
            # Positive when he has fallen past his market price — still on the
            # board after the room usually takes him. Negative when taking him
            # now would be ahead of where he usually goes.
            delta = current_pick - c.adp
            value = max(-ADP_REACH_CAP, min(ADP_VALUE_CAP, delta * ADP_VALUE_PER_PICK))
            score += value
            if delta >= 6:
                reasons.append(f"falling — ADP {c.adp:.0f}, on the board at {current_pick}")
            elif delta <= -6:
                reasons.append(f"a reach — ADP {c.adp:.0f} vs pick {current_pick}")

        # What waiting costs. Autodrafters walk a list and never start a run,
        # so a room that is half robots drains a position more slowly — the
        # same human_share that used to damp tier urgency damps this.
        if c.vona is not None and not held_back:
            urgency = max(0.0, min(SCARCITY_CAP, c.vona * SCARCITY_PER_POINT)) * human_share
            score += urgency
            # A room of robots never starts a run, so scarcity buys nothing —
            # and must not claim to. The reason follows the score, not the gap.
            if c.vona >= 12 and urgency > 0:
                reasons.append(
                    f"waiting costs ~{c.vona:.0f} pts — the next {c.position} likely "
                    "to reach your turn is well behind him"
                )
            elif c.vona <= 3 and human_until_turn:
                reasons.append(
                    f"{c.position} keeps — someone about as good should last to your next pick"
                )

        # Smallest term in the model, and the only one about other people.
        if c.list_vs_market is not None and not held_back:
            nudge = max(
                -LIST_VALUE_CAP,
                min(LIST_VALUE_CAP, c.list_vs_market * LIST_VALUE_PER_PICK),
            )
            score += nudge
            # list_vs_market is (blended ADP - mean list rank): positive means
            # the lists sit ABOVE the market on him.
            if c.list_vs_market >= 12:
                reasons.append(
                    f"list-followers reach for him — ranked ~{c.list_vs_market:.0f} "
                    "picks above his market price"
                )
            elif c.list_vs_market <= -12:
                reasons.append(
                    f"the lists are cold on him — ranked ~{abs(c.list_vs_market):.0f} "
                    "picks below his market price"
                )

        if c.tag:
            score += TAG_POINTS.get(c.tag, 0.0)
            if c.tag == "target":
                reasons.append("you tagged him a target")
            elif c.tag == "fade":
                reasons.append("you tagged him a fade")

        out.append(
            Recommendation(
                player_id=c.player_id,
                name=c.name,
                position=c.position,
                score=round(score, 1),
                vorp=round(c.vorp, 1),
                vona=None if c.vona is None else round(c.vona, 1),
                reasons=reasons,
            )
        )

    out.sort(key=lambda r: r.score, reverse=True)
    return out[:limit]
