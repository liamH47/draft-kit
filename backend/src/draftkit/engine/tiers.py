"""Gap-based tier cuts.

Sort a position's players by projected points descending; a new tier starts
wherever the drop to the next player exceeds a threshold. Cheap, explainable,
and good enough until a GMM variant earns its keep.
"""

from collections.abc import Sequence


def gap_tiers(points: Sequence[float], *, min_gap: float = 6.0) -> list[int]:
    """Assign 1-based tier numbers to a descending list of projected points."""
    tiers: list[int] = []
    tier = 1
    for i, pts in enumerate(points):
        if i > 0 and points[i - 1] - pts >= min_gap:
            tier += 1
        tiers.append(tier)
    return tiers
