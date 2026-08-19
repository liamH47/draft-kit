from itertools import pairwise

import pytest

from draftkit.engine.snake import (
    gap_after,
    my_pick_numbers,
    overall_pick,
    picks_until_my_turn,
    round_and_slot,
)


@pytest.mark.parametrize(
    ("round_no", "slot", "expected"),
    [
        (1, 1, 1),
        (1, 12, 12),
        (2, 12, 13),  # snake turns
        (2, 1, 24),
        (3, 1, 25),
        (3, 7, 31),
    ],
)
def test_overall_pick_12_team(round_no, slot, expected):
    assert overall_pick(round_no, slot, 12) == expected


@pytest.mark.parametrize("num_teams", [8, 10, 12, 14])
def test_round_and_slot_inverts_overall_pick(num_teams):
    for round_no in range(1, 16):
        for slot in range(1, num_teams + 1):
            overall = overall_pick(round_no, slot, num_teams)
            assert round_and_slot(overall, num_teams) == (round_no, slot)


@pytest.mark.parametrize("num_teams", [8, 10, 12, 14])
def test_every_overall_pick_used_exactly_once(num_teams):
    rounds = 15
    picks = [
        overall_pick(r, s, num_teams) for r in range(1, rounds + 1) for s in range(1, num_teams + 1)
    ]
    assert sorted(picks) == list(range(1, num_teams * rounds + 1))


@pytest.mark.parametrize("num_teams", [10, 12])
def test_gap_after_matches_consecutive_pick_difference(num_teams):
    for slot in range(1, num_teams + 1):
        picks = my_pick_numbers(num_teams, slot, 10)
        for round_no, (a, b) in enumerate(pairwise(picks), start=1):
            assert b - a == gap_after(round_no, slot, num_teams)


def test_turn_slots_get_back_to_back_picks():
    # Slot 1 leaving an even round, slot N leaving an odd round: gap of 1.
    assert gap_after(2, 1, 12) == 1
    assert gap_after(1, 12, 12) == 1
    # ...and the longest wait on the other side.
    assert gap_after(1, 1, 12) == 23
    assert gap_after(2, 12, 12) == 23


def test_picks_until_my_turn():
    # Slot 7 of 12: first pick is overall 7.
    assert picks_until_my_turn(12, 7, picks_made=0, rounds=15) == 6
    assert picks_until_my_turn(12, 7, picks_made=6, rounds=15) == 0  # on the clock
    assert picks_until_my_turn(12, 7, picks_made=7, rounds=15) == 10  # next is 18


def test_picks_until_my_turn_none_when_draft_done():
    assert picks_until_my_turn(12, 1, picks_made=12 * 15, rounds=15) is None
