"""What waiting costs: survival odds and value over the next available.

These are the numbers behind "take him now or take someone else" — the
single question a draft board exists to answer — so each piece is pinned
independently of the pool that feeds it.
"""

import pytest

from draftkit.engine.availability import (
    draft_spread,
    expected_best_available,
    survival,
    vona,
)


def test_a_player_the_room_takes_first_never_lasts():
    assert survival(1.6, 13, 0.8) < 0.001


def test_survival_falls_through_his_own_adp():
    """At his ADP it is a coin flip by construction; before it he is likely
    there, after it he is likely gone."""
    assert survival(50, 50) == pytest.approx(0.5)
    assert survival(50, 40) > 0.9
    assert survival(50, 60) < 0.1


def test_a_player_with_no_adp_is_assumed_available():
    """He is off the back of every market's list, which is the answer."""
    assert survival(None, 200) == 1.0


def test_nobody_is_gone_before_the_draft_starts():
    assert survival(1.0, 1) == 1.0
    assert survival(1.0, 0) == 1.0


def test_spread_uses_the_market_number_when_there_is_one():
    assert draft_spread(100, 20.0) == 20.0
    # ...and falls back to the shape the live market actually shows.
    assert draft_spread(100) == pytest.approx(11.0)
    # Nobody's slot is certain to a tenth of a pick, even at the very top.
    assert draft_spread(1.0) == 1.5
    assert draft_spread(100, 0.2) == 1.5


def test_expected_best_available_is_the_best_likely_survivor():
    """Two players: one certainly gone, one certainly there. The answer is
    the one who is there, not the better one."""
    gone = (100.0, 1.0, 0.5)
    survives = (60.0, 300.0, 5.0)
    assert expected_best_available([gone, survives], 40) == pytest.approx(60.0, abs=0.1)


def test_expected_best_available_of_nothing_is_nothing():
    assert expected_best_available([], 40) == 0.0


def test_vona_is_large_when_the_position_falls_off_a_cliff():
    """The user's question: the best QB is 30 points clear and the rest will
    be gone too, so waiting is expensive."""
    others = [(60.0, 44.0, 6.0), (58.0, 50.0, 6.0), (55.0, 60.0, 8.0)]
    assert vona(90.0, others, 37) > 25


def test_vona_is_small_when_someone_as_good_will_last():
    """The other half: if the seventh-best is barely worse and nobody is
    taking him, the first one is not worth a pick."""
    others = [(58.0, 200.0, 20.0), (57.0, 210.0, 20.0)]
    assert vona(60.0, others, 37) < 4


def test_vona_stops_once_the_rest_are_unreachable():
    """A long tail of certain survivors must not cost a full scan, and must
    not change the answer."""
    field = [(50.0 - i * 0.01, 400.0, 5.0) for i in range(500)]
    assert vona(60.0, field, 40) == pytest.approx(10.0, abs=0.1)
