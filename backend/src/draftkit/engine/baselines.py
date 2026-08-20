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
    out: dict[str, dict[str, float]] = {}
    for position, points in points_by_position.items():
        vols_index = round(league.num_teams * starters.get(position, 0))
        vorp_index = round(league.num_teams * depth.get(position, 0))
        out[position] = {
            "vols": _baseline_points(points, vols_index),
            "vorp": _baseline_points(points, vorp_index),
        }
    return out
