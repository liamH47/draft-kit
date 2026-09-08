"""Value-based drafting baselines.

Raw projected points can't be compared across positions — a 300-point QB and
a 300-point RB are worth very different things when every team must start a
QB but QB20 is freely available. Everything is therefore measured against a
replacement-level player at the same position:

  VOLS — vs the last player at the position who still starts for someone.
         Answers "how much better is he than what my weekly opponent starts?"
  VORP — vs the first player at the position nobody drafts.
         Answers "how much better is he than the waiver wire?"

Both baselines come from the league's own roster settings, so a 10-team
1-QB league and a 12-team superflex league get genuinely different answers.
"""

from draftkit.models.league import LeagueConfig, RosterSlots

# How much of the ordering value comes from VOLS. Pure VORP sits in the
# projection tail, where preseason numbers crater at some positions (RB53
# projects ~74 points in a 12-team league) but not others (WR53 ~126) - a
# projection artifact, not a scarcity fact, and at an even blend half of it
# passed through as a flat ~28-point subsidy to every RB over every WR
# (Derrick Henry, ADP 18, outranked Ja'Marr Chase, ADP 4). Weighting VOLS
# keeps VORP's waiver-wire logic while anchoring value to players someone
# actually starts. Within-position order is untouched by construction: a
# baseline is a constant shift.
VALUE_VOLS_WEIGHT = 0.75

FLEX_ELIGIBLE = ("RB", "WR", "TE")
# Bench spots are hoarded at the positions people handcuff and stash; nobody
# carries a backup kicker or defense.
BENCH_ELIGIBLE = ("QB", "RB", "WR", "TE")


def starters_by_position(roster: RosterSlots) -> dict[str, float]:
    """Starting spots per team per position, with flex spread over the
    positions that actually fill it (fractional on purpose)."""
    base: dict[str, float] = {
        "QB": float(roster.qb),
        "RB": float(roster.rb),
        "WR": float(roster.wr),
        "TE": float(roster.te),
        "K": float(roster.k),
        "DEF": float(roster.dst),
    }
    if roster.flex:
        total = sum(base[p] for p in FLEX_ELIGIBLE)
        if total:
            for p in FLEX_ELIGIBLE:
                base[p] += roster.flex * base[p] / total
    # A superflex is a QB slot in all but name — treating it as anything else
    # badly under-prices quarterbacks, which is the whole point of the format.
    base["QB"] += float(roster.superflex)
    return base


def drafted_by_position(roster: RosterSlots) -> dict[str, float]:
    """Roster spots per team per position once benches fill up."""
    starters = starters_by_position(roster)
    depth = dict(starters)
    if roster.bench:
        total = sum(starters[p] for p in BENCH_ELIGIBLE)
        if total:
            for p in BENCH_ELIGIBLE:
                depth[p] += roster.bench * starters[p] / total
    return depth


def _baseline_points(points_desc: list[float], index: int) -> float:
    """Points for the replacement player, clamped to the ends of the list."""
    if not points_desc:
        return 0.0
    return points_desc[min(max(index, 0), len(points_desc) - 1)]


# Replacement for a position nobody benches is not the last starter — it is
# whatever is on waivers, and for kickers and defenses that is very nearly as
# good as the best of them. Twelve teams roster twelve kickers and the other
# thirty-three sit free, so a manager streams the best matchup every week
# rather than holding one all season.
#
# Measured, this is the board's largest single defect. Baselining kickers and
# defenses at the last starter put twenty-two of them inside the top 120 and
# the best at board rank 46 — round four — while expert consensus ranks every
# one of them past 180. That is what produced a team defense in the engine's
# top three in round eight of a live draft.
#
# Which positions get this treatment is not hard-coded: late_round_positions
# already states which ones the league believes should wait, and this makes
# the VALUE arithmetic agree with that stated belief instead of contradicting
# it. A league that genuinely drafts kickers early can empty the list.
STREAMED_BASELINE_INDEX = 0


def baselines(
    league: LeagueConfig, points_by_position: dict[str, list[float]]
) -> dict[str, dict[str, float]]:
    """Per-position VOLS and VORP baseline point totals.

    points_by_position holds each position's projected points sorted
    descending. Index n (0-based) is the (n+1)th best player, so the first
    player past the starters is exactly index = teams * starters.
    """
    starters = starters_by_position(league.roster)
    depth = drafted_by_position(league.roster)
    streamed = set(league.late_round_positions)
    out: dict[str, dict[str, float]] = {}
    for position, points in points_by_position.items():
        if position in streamed:
            # Value over "the best one I could stream" — near zero for
            # everybody, which is what makes these sort to the tail where the
            # market has always had them.
            replacement = _baseline_points(points, STREAMED_BASELINE_INDEX)
            out[position] = {"vols": replacement, "vorp": replacement, "value": replacement}
            continue
        vols_index = round(league.num_teams * starters.get(position, 0))
        vorp_index = round(league.num_teams * depth.get(position, 0))
        vols = _baseline_points(points, vols_index)
        vorp = _baseline_points(points, vorp_index)
        out[position] = {
            "vols": vols,
            "vorp": vorp,
            # What the score measures against and the board orders by; see
            # VALUE_VOLS_WEIGHT for why the blend leans VOLS.
            "value": VALUE_VOLS_WEIGHT * vols + (1 - VALUE_VOLS_WEIGHT) * vorp,
        }
    return out
