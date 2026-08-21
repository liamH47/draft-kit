"""Will he still be there next time I pick?

The most valuable thing a draft board can tell you is not who is best — it is
what waiting costs. If the best quarterback is 40 points clear of the seventh
and the seventh will be gone too, that gap is real and you should pay for it.
If the seventh is four points worse and will still be sitting there two rounds
later, the first one is a trap however highly he is rated.

That number is VONA: value over the next available player at the same
position, measured at your NEXT pick rather than this one. It is the honest
form of positional scarcity, because it prices the position's drop-off against
the specific gap you are about to sit through.

Draft position is treated as normal around a player's ADP. The spread is his
own when the market reports one (FantasyFootballCalculator publishes a real
standard deviation); otherwise it comes from the shape the live data shows —
spread runs about 0.11 x ADP, with a floor for the very top of the board where
there is nowhere left to fall.

All pure functions over plain numbers: no I/O, no clock, no league.
"""

from collections.abc import Sequence
from operator import itemgetter
from statistics import NormalDist

# Fitted to 225 FFC players with a published stdev: the ratio holds near 0.11
# from pick 12 to pick 200, and the floor keeps the top of the board sane
# (nobody's draft slot is certain to a tenth of a pick).
_SPREAD_RATIO = 0.11
_MIN_SPREAD = 1.5

_NORMAL = NormalDist()


def draft_spread(adp: float, stdev: float | None = None) -> float:
    """How tightly the room agrees on where a player goes."""
    if stdev is not None and stdev > 0:
        return max(stdev, _MIN_SPREAD)
    return max(_MIN_SPREAD, _SPREAD_RATIO * adp)


def survival(adp: float | None, at_pick: int, stdev: float | None = None) -> float:
    """Probability a player is still on the board when pick `at_pick` arrives.

    A player nobody has an ADP for is off the back of every market's list,
    which is itself the answer: he will be there.
    """
    if adp is None:
        return 1.0
    if at_pick <= 1:
        return 1.0
    spread = draft_spread(adp, stdev)
    # He survives to this pick if his true draft slot lands after it.
    return 1.0 - _NORMAL.cdf((at_pick - adp) / spread)


def expected_best_available(
    players: Sequence[tuple[float, float | None, float | None]], at_pick: int
) -> float:
    """Expected value of the best player left at a position by `at_pick`.

    `players` is (value, adp, stdev), any order. Walking best-first, the best
    survivor is the first player who lasts, so his contribution is his value
    times the chance he lasts times the chance everyone better did not.
    Independence across players is an approximation — a run at a position is
    correlated — but it errs toward assuming the position drains, which is the
    safe direction for a draft board.
    """
    # itemgetter over a lambda: this runs once per available player per board
    # read, and the input is usually already in value order.
    ordered = sorted(players, key=itemgetter(0), reverse=True)
    expected = 0.0
    all_better_gone = 1.0
    for value, adp, stdev in ordered:
        p_survives = survival(adp, at_pick, stdev)
        expected += value * p_survives * all_better_gone
        all_better_gone *= 1.0 - p_survives
        if all_better_gone < 1e-6:  # everyone after this is unreachable
            break
    return expected


def vona(
    value: float,
    others_at_position: Sequence[tuple[float, float | None, float | None]],
    at_pick: int,
) -> float:
    """Value over the next available: what taking him now buys over waiting.

    Near zero means the position keeps: someone about as good is very likely to
    survive your next pick, so spend the pick elsewhere. Large means the
    drop-off behind him is real and about to be taken by somebody else.
    """
    return value - expected_best_available(others_at_position, at_pick)
