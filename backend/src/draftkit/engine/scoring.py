"""Pure scoring math: raw stat line + scoring settings -> fantasy points."""

from draftkit.models.league import ScoringSettings


def score(stats: dict[str, float], scoring: ScoringSettings) -> float:
    return round(sum(value * scoring.weights.get(stat, 0.0) for stat, value in stats.items()), 2)
