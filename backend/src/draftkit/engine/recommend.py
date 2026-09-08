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
  injury            — a man who will not play scores nothing, whatever his
                      projection says
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
# A target is a thumb on the scale — worth more than a full unfilled starting
# slot, and still losable to a genuinely better player.
#
# A fade is not a discount, it is a veto. At -30 it was a discount: on a board
# whose top spans 250 points it left a faded player leading the
# recommendations by a single point, and which side of that line he landed on
# moved every time anything else in the model did. The user saying "not this
# man" should not be a coin flip, so the fade is deliberately larger than
# every other term here combined — the same trick LATE_ROUND_PENALTY plays on
# one position, applied to the whole board.
TAG_POINTS = {"target": 22.0, "at_adp": 0.0, "fade": -1000.0}
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
# A projection forecasts what a player would do IF HE PLAYS. It does not know
# he is on IR, so without this the board will happily lead with a man who is
# out for the year. Two buckets, because they are genuinely different problems:
#
#   season-ending — he is not coming back in time to matter. Sink him beneath
#                   any healthy player worth the pick.
#   provisional   — he is hurt now and may well be active in week one. Preseason
#                   PUP is the common case: a real risk and a real discount, not
#                   a write-off. Grading these the same cost George Kittle four
#                   rounds for an Achilles he was expected to return from.
#
# Both leave him on the board with his designation shown. Neither is large
# enough to stop the user tagging him a target and overriding the lot.
# Compared case-folded: the feed is not contractually stable about casing.
SEASON_ENDING_STATUSES = frozenset({"IR", "DNR", "SUS", "SUSPENDED"})
PROVISIONAL_STATUSES = frozenset({"PUP", "NA", "COV", "OUT"})
SEASON_ENDING_PENALTY = 45.0
PROVISIONAL_PENALTY = 20.0
# Questionable and Doubtful are week-to-week noise months before kickoff. They
# are shown on the board and deliberately never scored.

# How far the score is allowed to sit from the room's consensus without a
# reason it can name.
#
# Nothing else in the model checks the board's ORDERING against the published
# one. The ADP term measures displacement — has he fallen past his price? — and
# at the top of a draft that is nearly zero for everyone, so a projection
# artifact at a whole position went completely unchallenged. In a superflex
# league the board had six quarterbacks in its top 24 against consensus' 13,
# and nothing in the score noticed.
#
# The correction is deliberately expressed in POINTS AT THAT BOARD SLOT rather
# than points-per-rank: one rank is worth ~9 points at the top of the board and
# ~1 point by pick 100, so a flat per-rank rate would overcorrect the tail and
# barely move the round where it matters. Consensus' opinion is read as "this
# player belongs in that slot", and the slot's value is what the pull is
# measured against.
#
# TRUST is well under half on purpose. Consensus cannot know this league's
# scoring — first downs are worth ~33 points of value to an elite back here and
# ~12 to a quarterback, and a generic board prices none of it. The cap then
# keeps a nameable signal decisive: roster need (18) plus wait cost (16) still
# outweighs the largest possible anchor, so the case the anchor must never
# block — a run on quarterbacks in superflex when you still need one — still
# gets through.
CONSENSUS_TRUST = 0.35
CONSENSUS_CAP = 25.0
# Below this the gap is ordinary disagreement and saying so would be noise.
CONSENSUS_REASON_POINTS = 8.0


@dataclass
class Candidate:
    player_id: str
    name: str
    position: str
    points: float
    vorp: float
    adp: float | None = None
    tag: str | None = None
    # Positive when ranking lists sit above the market on him: list-followers
    # (autodrafters, anyone drafting off the platform's default order) reach for
    # him sooner than the market would.
    list_vs_market: float | None = None
    # Value over the next available player at his position, measured at my
    # NEXT pick. Near zero means the position keeps and the pick is better
    # spent elsewhere; large means the drop-off behind him is real.
    vona: float | None = None
    # Sleeper's injury designation, verbatim. See OUT_STATUSES.
    injury_status: str | None = None
    # Where the published lists put him. Only lists that priced THIS format
    # reach here — a one-QB board is not a noisy superflex opinion, it is a
    # confident opinion about a different game.
    consensus_rank: float | None = None


@dataclass
class Recommendation:
    player_id: str
    name: str
    position: str
    score: float
    # The board's value number (the VOLS-leaning blend), NOT true VORP -
    # QuickEntry shows real VORP under that name, so this one must not.
    value: float
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


def _consensus_pull(available: list[Candidate]) -> dict[str, float]:
    """Points to move each candidate toward where the published lists put him.

    Both orderings are taken over the same cohort — the players still on the
    board who carry a consensus rank — so the value ladder the pull is read
    off is the one this board actually offers, and neither ordering is mixed
    with a subset it was not measured against.
    """
    cohort = [c for c in available if c.consensus_rank is not None]
    if not cohort:
        return {}
    # What the Nth-best slot on this board is worth, by the model's own numbers.
    ladder = sorted((c.vorp for c in cohort), reverse=True)
    pull: dict[str, float] = {}
    for slot, c in enumerate(sorted(cohort, key=lambda c: c.consensus_rank or 0.0)):
        delta = ladder[slot] - c.vorp
        pull[c.player_id] = max(-CONSENSUS_CAP, min(CONSENSUS_CAP, CONSENSUS_TRUST * delta))
    return pull


def recommend(
    available: list[Candidate],
    *,
    league,
    my_counts: dict[str, int],
    current_pick: int,
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

    consensus_pull = _consensus_pull(available)

    out: list[Recommendation] = []
    for c in available:
        score = c.vorp
        reasons: list[str] = []

        # Before anything else: can he play? A hurt player still carries his
        # full projection, because a projection cannot know. Say so out loud —
        # a name that quietly sinks down the board reads as a bug mid-draft.
        status = (c.injury_status or "").upper()
        if status in SEASON_ENDING_STATUSES:
            score -= SEASON_ENDING_PENALTY
            reasons.append(f"{c.injury_status} — out for the season; a stash at best")
        elif status in PROVISIONAL_STATUSES:
            score -= PROVISIONAL_PENALTY
            reasons.append(f"{c.injury_status} — hurt now, and may not open the season")

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
        # The wait-cost itself is the card's lead line, rendered from the
        # structured vona field - duplicating it as a reason string is what
        # used to bury it in the bullet list.
        if c.vona is not None and not held_back:
            urgency = max(0.0, min(SCARCITY_CAP, c.vona * SCARCITY_PER_POINT)) * human_share
            score += urgency

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

        # Where this board disagrees with the room, and by how much. Held-back
        # players are exempt: their score is deliberately not their value, so
        # pulling them toward a consensus that also buries them is noise.
        # Tagged players are NOT exempt — the pull depends only on his value
        # and his consensus rank, neither of which a tag changes, so applying
        # it to everyone is what keeps a tag worth exactly its face value.
        pull = 0.0 if held_back else consensus_pull.get(c.player_id, 0.0)
        if pull:
            score += pull
            if pull >= CONSENSUS_REASON_POINTS:
                reasons.append(
                    "the published boards rate him well above this one — "
                    "consensus has him going considerably earlier"
                )
            elif pull <= -CONSENSUS_REASON_POINTS:
                reasons.append(
                    "this board is alone on him — the published boards have him "
                    "meaningfully later, so the edge here is a projection call"
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
                value=round(c.vorp, 1),
                vona=None if c.vona is None else round(c.vona, 1),
                reasons=reasons,
            )
        )

    out.sort(key=lambda r: r.score, reverse=True)
    return out[:limit]
