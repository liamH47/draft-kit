"""Score the value model against expert consensus, so tuning stops being taste.

The board's ordering is a claim: "these players, in this order, are what your
league should want." That claim can be wrong in two different ways, and they
need separating before anything is tuned.

  WITHIN a position - does the model agree about who is good? Measured by
  Spearman against ECR. Currently 0.96-0.98 everywhere, so the projections
  are fine and this is not where the problems are.

  ACROSS positions - does the board mix positions the way the market does?
  This is entirely a baselines question, and it is where the board goes wrong.

ECR is the reference, not the truth. It is a hundred-odd analysts who have
priced roster construction, injury risk and role certainty in a way season
projections cannot. Matching it exactly would make the model pointless; being
120 ranks away from it at a whole position is a bug rather than an edge. This
script measures the distance so the difference between the two is a number.

Run: uv run python scripts/eval_baselines.py
"""

import statistics as st
from dataclasses import dataclass
from pathlib import Path

import draftkit.pool as pool_mod
from draftkit.config import get_settings
from draftkit.engine import baselines as B
from draftkit.models.league import LeagueConfig, RosterSlots, ScoringSettings
from draftkit.pool import build_pool
from draftkit.snapshots.store import SnapshotStore

OVERRIDES = Path(__file__).parent.parent / "src" / "draftkit" / "identity" / "overrides.yaml"
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")


@dataclass
class Result:
    label: str
    mix: dict[int, dict[str, int]]  # cutoff -> position counts
    median_diff: dict[str, float]  # position -> median (model rank - ECR rank)
    kd_best_rank: int  # board rank of the best K/DEF; ECR puts these ~130+


def evaluate(players, label: str, cutoffs=(36, 60, 120)) -> Result:
    ranked = [p for p in players if p.rank_by_source.get("fantasypros")]
    mix = {}
    for n in cutoffs:
        top = sorted(ranked, key=lambda p: p.rank)[:n]
        counts = dict.fromkeys(POSITIONS, 0)
        for p in top:
            counts[p.position] += 1
        mix[n] = counts
    med = {}
    # Only the draftable range: past ECR ~180 the two lists are measuring
    # different things and the median just reports tail noise.
    ranked = [p for p in ranked if p.rank_by_source["fantasypros"] <= 180]
    for pos in POSITIONS:
        at = [p for p in ranked if p.position == pos]
        if at:
            med[pos] = st.median(p.rank - p.rank_by_source["fantasypros"] for p in at)
    kd = [p for p in players if p.position in ("K", "DEF")]
    return Result(label, mix, med, min((p.rank for p in kd), default=0))


def ecr_mix(players, cutoffs=(36, 60, 120)) -> dict[int, dict[str, int]]:
    ranked = [p for p in players if p.rank_by_source.get("fantasypros")]
    out = {}
    for n in cutoffs:
        top = sorted(ranked, key=lambda p: p.rank_by_source["fantasypros"])[:n]
        counts = dict.fromkeys(POSITIONS, 0)
        for p in top:
            counts[p.position] += 1
        out[n] = counts
    return out


def superflex_report(store, settings) -> None:
    """The format the value model is worst at, kept measured rather than
    remembered.

    A second quarterback slot is where every wrong assumption in this codebase
    showed up at once, so this section exists to catch the next one. Three
    separate defects fed it and none of them announced itself:

      the MARKET was a one-QB market. Sleeper's half-PPR ADP has Josh Allen at
      20.9 where its own two-QB list has him at 3.4, so the score charged a
      thirty-point reach to anyone taking a quarterback at his real price and
      the survival model — which decides wait cost — thought every one of them
      would last another turn.

      the CONSENSUS was a one-QB consensus. ESPN, CBS and Boris Chen publish
      no superflex board, and averaged in they outvoted the one list that did,
      two to one.

      and nothing compared the board's ORDERING to that consensus at all, so
      the gap below could grow to seven quarterbacks wide unchallenged.

    The headline number is quarterbacks inside the top 24 — the first two
    rounds, where the format is actually decided.
    """
    league = LeagueConfig(
        name="superflex eval",
        num_teams=10,
        my_slot=1,
        scoring=ScoringSettings.preset("half_ppr"),
        roster=RosterSlots(qb=1, rb=2, wr=2, te=1, flex=1, superflex=1, k=1, dst=1, bench=7),
    )
    # Run it twice. The second league scores rushing and receiving first downs,
    # which is the shape of the user's own superflex league and the single
    # biggest legitimate reason for this board to disagree with a published
    # one: ECR is a GENERIC superflex order and cannot know the rule exists.
    # Seeing both makes the difference between "the model has a reason" and
    # "the model has a bug" a number rather than an argument.
    first_downs = league.model_copy(deep=True)
    first_downs.scoring.weights["rush_fd"] = 1.0
    first_downs.scoring.weights["rec_fd"] = 1.0

    def mix_of(players, key, n):
        counts = dict.fromkeys(POSITIONS, 0)
        for p in sorted(players, key=key)[:n]:
            counts[p.position] += 1
        return counts

    boards = {}
    for label, config in (("plain", league), ("first downs", first_downs)):
        built = build_pool(
            store,
            config,
            season=settings.season,
            scoring_preset="half_ppr",
            overrides_path=OVERRIDES,
        ).players
        boards[label] = [p for p in built if p.rank_by_source.get("fantasypros")]

    ranked = boards["plain"]
    if not ranked:
        print("SUPERFLEX - no superflex ECR snapshot; run warm_snapshots.py first")
        return

    print("SUPERFLEX (10 teams, 1 superflex slot) - board mix vs superflex ECR")
    print(f"{'':21}{'QB':>5}{'RB':>5}{'WR':>5}{'TE':>5}")
    for n in (24, 36, 60, 100):
        ecr = mix_of(ranked, lambda p: p.rank_by_source["fantasypros"], n)
        row = "".join(f"{ecr[x]:>5}" for x in ("QB", "RB", "WR", "TE"))
        print(f"  top {n:>3}  {'ECR':<11}{row}")
        for label in ("plain", "first downs"):
            board = mix_of(boards[label], lambda p: p.rank, n)
            row = "".join(f"{board[x]:>5}" for x in ("QB", "RB", "WR", "TE"))
            print(f"{'':10} {label:<11}{row}")

    # The consensus must be the superflex one, not an average that includes
    # three one-QB boards. If this drifts, so has the advice.
    leaked = [
        p.name
        for p in ranked[:40]
        if p.consensus_rank is not None
        and p.rank_by_source.get("fantasypros") is not None
        and abs(p.consensus_rank - p.rank_by_source["fantasypros"]) > 0.05
    ]
    print(
        f"  consensus == superflex ECR for the top 40: {not leaked}"
        + (f" (leaked: {leaked[:3]})" if leaked else "")
    )
    print()


def main() -> int:
    settings = get_settings()
    store = SnapshotStore(settings.snapshots_dir, offline=True)
    superflex_report(store, settings)
    league = LeagueConfig(
        name="eval",
        num_teams=12,
        my_slot=1,
        scoring=ScoringSettings.preset("half_ppr"),
        roster=RosterSlots(qb=1, rb=2, wr=2, te=1, flex=1, k=1, dst=1, bench=6),
    )

    def pool():
        return build_pool(
            store,
            league,
            season=settings.season,
            scoring_preset="half_ppr",
            overrides_path=OVERRIDES,
        ).players

    baseline_players = pool()
    reference = ecr_mix(baseline_players)
    print("REFERENCE - how ECR mixes positions")
    for n, c in reference.items():
        print(f"  top {n:>3}: {c}")
    print()

    results = [evaluate(baseline_players, "current")]

    # --- sweep 1: how much of value comes from VOLS -----------------------
    # Raising this leans on "the last player someone starts" and away from the
    # projection tail, which is where the RB curve craters for reasons that
    # are about roster uncertainty rather than scarcity.
    original_weight = B.VALUE_VOLS_WEIGHT
    for w in (0.5, 0.75, 0.9, 1.0):
        B.VALUE_VOLS_WEIGHT = w
        results.append(evaluate(pool(), f"vols_weight={w}"))
    B.VALUE_VOLS_WEIGHT = original_weight

    # --- sweep 2: a streaming baseline for K and DEF ----------------------
    # Nobody benches a kicker, so every kicker past the starters sits on
    # waivers and you take the best matchup each week. Replacement for a
    # streamed position is therefore near the TOP of it, not at the last
    # starter. Depth is expressed as a fraction of the starter count.
    original_baselines = pool_mod.baselines

    def streamed(fraction: float):
        def patched(lg, points_by_position):
            out = original_baselines(lg, points_by_position)
            for pos in ("K", "DEF"):
                pts = sorted(points_by_position.get(pos, []), reverse=True)
                if not pts:
                    continue
                idx = max(0, min(len(pts) - 1, round(lg.num_teams * fraction) - 1))
                out[pos] = {"vols": pts[idx], "vorp": pts[idx], "value": pts[idx]}
            return out

        return patched

    for frac in (0.5, 0.25, 0.0):
        pool_mod.baselines = streamed(frac)
        results.append(evaluate(pool(), f"K/DEF baseline at top {frac:.0%} of starters"))
    pool_mod.baselines = original_baselines

    # --- sweep 3: take VORP depth from the market, not from roster shape --
    # drafted_by_position splits the bench in proportion to starters, so with
    # 2 RB and 2 WR it assumes both are rostered equally deep. Real drafts do
    # not: our own 12-team league rostered 62 RBs and 73 WRs. If the market
    # carries more receivers, the WR baseline sits deeper and every receiver
    # is worth more than the roster-shape assumption implies.
    def market_depth(players):
        drafted = {}
        cap = league.num_teams * 15
        for p in players:
            if p.adp and p.adp <= cap:
                drafted[p.position] = drafted.get(p.position, 0) + 1
        return drafted

    depths = market_depth(baseline_players)
    print("market-observed drafted counts (ADP inside 15 rounds):", depths)
    print()

    def from_market(depths):
        def patched(lg, points_by_position):
            out = original_baselines(lg, points_by_position)
            for pos, pts in points_by_position.items():
                n = depths.get(pos)
                if not n or pos in ("K", "DEF"):
                    continue
                arr = sorted(pts, reverse=True)
                idx = max(0, min(len(arr) - 1, n - 1))
                vols = out[pos]["vols"]
                out[pos] = {
                    "vols": vols,
                    "vorp": arr[idx],
                    "value": B.VALUE_VOLS_WEIGHT * vols + (1 - B.VALUE_VOLS_WEIGHT) * arr[idx],
                }
            return out

        return patched

    pool_mod.baselines = from_market(depths)
    results.append(evaluate(pool(), "VORP depth from market ADP"))
    pool_mod.baselines = original_baselines

    print("SWEEP - distance from the reference")
    print(f"{'config':44}{'top36 RB/WR':>14}{'K+DEF in top120':>18}{'best K/DEF rank':>18}")
    ref36 = reference[36]
    print(
        f"{'ECR (reference)':44}{f'{ref36[chr(82) + chr(66)]}/{ref36[chr(87) + chr(82)]}':>14}"
        f"{reference[120]['K'] + reference[120]['DEF']:>18}{'n/a':>18}"
    )
    for r in results:
        m36, m120 = r.mix[36], r.mix[120]
        print(
            f"{r.label:44}{f'{m36[chr(82) + chr(66)]}/{m36[chr(87) + chr(82)]}':>14}"
            f"{m120['K'] + m120['DEF']:>18}{r.kd_best_rank:>18}"
        )
    print()
    print("median (model rank - ECR rank) by position; 0 means the board agrees")
    print(f"{'config':44}" + "".join(f"{p:>7}" for p in POSITIONS))
    for r in results:
        print(f"{r.label:44}" + "".join(f"{r.median_diff.get(p, 0):>7.0f}" for p in POSITIONS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
