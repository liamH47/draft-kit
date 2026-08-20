"""Ranked pick recommendations, with the reasoning shown.

A number nobody understands is a number nobody trusts mid-draft, so every
candidate carries the plain-English reasons behind its score. The score is a
sum of interpretable parts:

  VORP              — the backbone: value over a replacement-level player
  roster need       — unfilled starting slots, decaying as they fill
  ADP value         — is he falling past his market price, or a reach?
  tier urgency      — will this tier survive until my next turn?
  your own tags     — target / at-ADP / fade override the market entirely

All pure functions over plain data: no I/O, no database, no clock.
"""

from dataclasses import dataclass, field

from draftkit.engine.baselines import starters_by_position

# Tunables. Units are fantasy points, so they're comparable to VORP directly.
NEED_BONUS = 18.0  # a fully unfilled starting slot is worth this much
ADP_VALUE_PER_PICK = 0.6  # points per pick a player has fallen past his ADP
ADP_VALUE_CAP = 12.0  # ...but a 40-pick faller isn't 40 picks better
TIER_URGENCY_BONUS = 14.0  # his tier probably won't survive to my next turn
TAG_POINTS = {"target": 22.0, "at_adp": 0.0, "fade": -30.0}


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


@dataclass
class Recommendation:
    player_id: str
    name: str
    position: str
    score: float
    vorp: float
    reasons: list[str] = field(default_factory=list)


def _need_factor(position: str, my_counts: dict[str, int], starters: dict[str, float]) -> float:
    """1.0 when no starting slot at the position is filled, 0.0 once they are."""
    needed = starters.get(position, 0.0)
    if needed <= 0:
        return 0.0
    filled = my_counts.get(position, 0)
    return max(0.0, (needed - filled) / needed)


def recommend(
    available: list[Candidate],
    *,
    league,
    my_counts: dict[str, int],
    current_pick: int,
    picks_until_turn: int | None,
    limit: int = 5,
) -> list[Recommendation]:
    starters = starters_by_position(league.roster)

    # How many players remain in each (position, tier) — the input to urgency.
    tier_counts: dict[tuple[str, int], int] = {}
    for c in available:
        if c.tier is not None:
            key = (c.position, c.tier)
            tier_counts[key] = tier_counts.get(key, 0) + 1

    out: list[Recommendation] = []
    for c in available:
        score = c.vorp
        reasons: list[str] = []

        if c.vorp > 0:
            reasons.append(f"{c.vorp:+.0f} pts over a replacement {c.position}")

        need = _need_factor(c.position, my_counts, starters)
        if need > 0:
            bonus = NEED_BONUS * need
            score += bonus
            filled = my_counts.get(c.position, 0)
            want = starters.get(c.position, 0)
            reasons.append(f"you still need {c.position} starters ({filled:.0f}/{want:.0f} filled)")

        if c.adp is not None:
            delta = c.adp - current_pick
            value = max(-ADP_VALUE_CAP, min(ADP_VALUE_CAP, delta * ADP_VALUE_PER_PICK))
            score += value
            if delta >= 6:
                reasons.append(f"falling — ADP {c.adp:.0f}, on the board at {current_pick}")
            elif delta <= -6:
                reasons.append(f"a reach — ADP {c.adp:.0f} vs pick {current_pick}")

        if c.tier is not None and picks_until_turn:
            left = tier_counts.get((c.position, c.tier), 0)
            if left <= picks_until_turn:
                score += TIER_URGENCY_BONUS
                plural = "player" if left == 1 else "players"
                reasons.append(
                    f"only {left} {plural} left in {c.position} tier {c.tier}, "
                    f"{picks_until_turn} picks until your turn"
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
                reasons=reasons,
            )
        )

    out.sort(key=lambda r: r.score, reverse=True)
    return out[:limit]
