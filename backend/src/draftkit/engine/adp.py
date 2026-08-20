"""ADP blending across sources."""


def blend_adp(adp_by_source: dict[str, float], weights: dict[str, float]) -> float | None:
    """Weighted mean over the sources present; None if none are."""
    present = {s: v for s, v in adp_by_source.items() if v is not None}
    if not present:
        return None
    total_weight = sum(weights.get(s, 1.0) for s in present)
    if total_weight <= 0:
        return None
    return round(sum(v * weights.get(s, 1.0) for s, v in present.items()) / total_weight, 1)


def list_vs_market(rank_by_source: dict[str, float], blended_adp: float | None) -> float | None:
    """How far a player's ranking lists sit from where he actually goes.

    Positive means the lists are higher on him than the market is: expect him
    to be available later than his list rank suggests, and expect list-followers
    (autodrafters, and anyone drafting off the platform's default order) to take
    him sooner than the market would.

    This measures where a room will *behave*, never how good a player is — the
    projections already answer that, and mixing the two double-counts one
    opinion. Treat it as a small tiebreaker, not a price.
    """
    if not rank_by_source or blended_adp is None:
        return None
    mean_rank = sum(rank_by_source.values()) / len(rank_by_source)
    return round(blended_adp - mean_rank, 1)
