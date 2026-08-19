"""Snake-draft pick arithmetic.

Rounds alternate direction: in odd rounds slot 1 picks first, in even rounds
slot N does. Everything dynamic in the app (how urgent a tier break is, who
survives to your next turn) keys off "how many picks until my turn", so this
module is deliberately tiny and exhaustively tested.
"""


def overall_pick(round_no: int, slot: int, num_teams: int) -> int:
    """1-based overall pick number for a slot in a given round."""
    if round_no % 2 == 1:
        return (round_no - 1) * num_teams + slot
    return (round_no - 1) * num_teams + (num_teams - slot + 1)


def round_and_slot(overall: int, num_teams: int) -> tuple[int, int]:
    """Inverse of overall_pick: 1-based (round, slot) for an overall pick."""
    round_no = (overall - 1) // num_teams + 1
    index = (overall - 1) % num_teams + 1
    slot = index if round_no % 2 == 1 else num_teams - index + 1
    return round_no, slot


def gap_after(round_no: int, slot: int, num_teams: int) -> int:
    """Picks between this slot's pick in round_no and its next pick.

    The classic snake identities: 2(N-p)+1 leaving an odd round, 2p-1 leaving
    an even round. At the turn (slot 1 or N) one of these is 1 — back-to-back
    picks — and the other is the long wait.
    """
    if round_no % 2 == 1:
        return 2 * (num_teams - slot) + 1
    return 2 * slot - 1


def my_pick_numbers(num_teams: int, slot: int, rounds: int) -> list[int]:
    return [overall_pick(r, slot, num_teams) for r in range(1, rounds + 1)]


def picks_until_my_turn(num_teams: int, slot: int, picks_made: int, rounds: int) -> int | None:
    """Other teams' picks between now and my next turn.

    picks_made is how many picks are already in the log, so the pick on the
    clock is number picks_made + 1. Returns 0 when I'm on the clock, and None
    once I have no picks left in the draft.
    """
    on_the_clock = picks_made + 1
    for pick in my_pick_numbers(num_teams, slot, rounds):
        if pick >= on_the_clock:
            return pick - on_the_clock
    return None
