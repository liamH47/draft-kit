"""The single entry point every pick producer calls.

Manual entry, the Sleeper poller, and a future browser extension all land
here, so dedup, snake math and event fan-out are written once. Adding a
producer later is an adapter, not a new code path.
"""

import sqlite3

from draftkit.engine.snake import round_and_slot
from draftkit.models.pick import Pick


class DuplicatePick(Exception):
    """That player is already off the board in this session."""


class DraftComplete(Exception):
    """Every roster spot in the draft is filled."""


def record_pick(
    conn: sqlite3.Connection,
    session: dict,
    league: dict,
    player_id: str,
    *,
    source: str = "manual",
    is_mine: bool | None = None,
) -> Pick:
    from draftkit.db import repo

    picks = repo.live_picks(conn, session["id"])
    if any(p["player_id"] == player_id for p in picks):
        raise DuplicatePick(player_id)

    num_teams: int = league["num_teams"]
    total = num_teams * league["rounds"]
    overall_no = len(picks) + 1
    if overall_no > total:
        raise DraftComplete(f"draft is {total} picks long")

    round_no, slot = round_and_slot(overall_no, num_teams)
    if is_mine is None:
        is_mine = slot == league["my_slot"]

    row = repo.append_pick(
        conn,
        session["id"],
        {
            "overall_no": overall_no,
            "round_no": round_no,
            "slot": slot,
            "player_id": player_id,
            "is_mine": is_mine,
            "source": source,
        },
    )
    return Pick(**{**row, "is_mine": bool(row["is_mine"]), "undone": bool(row["undone"])})


class NoSuchPick(Exception):
    """That pick number has not been made in this session."""


def correct_pick(
    conn: sqlite3.Connection,
    session: dict,
    league: dict,
    overall_no: int,
    player_id: str,
) -> Pick:
    """Replace the player recorded at one pick number.

    Mistyping pick 43 and noticing at 51 should cost one correction, not nine
    undos and nine re-entries while the room keeps drafting. The wrong pick is
    tombstoned rather than deleted, so the log still shows what happened.
    """
    from draftkit.db import repo

    picks = repo.live_picks(conn, session["id"])
    if any(p["player_id"] == player_id and p["overall_no"] != overall_no for p in picks):
        raise DuplicatePick(player_id)

    previous = repo.tombstone_pick_at(conn, session["id"], overall_no)
    if previous is None:
        raise NoSuchPick(f"pick {overall_no} has not been made")

    row = repo.append_pick(
        conn,
        session["id"],
        {
            "overall_no": overall_no,
            "round_no": previous["round_no"],
            "slot": previous["slot"],
            "player_id": player_id,
            # Whose pick it was is a property of the slot, not of who was
            # mistakenly recorded in it.
            "is_mine": previous["slot"] == league["my_slot"],
            "source": "correction",
        },
    )
    return Pick(**{**row, "is_mine": bool(row["is_mine"]), "undone": bool(row["undone"])})


def undo_last_pick(conn: sqlite3.Connection, session: dict) -> Pick | None:
    from draftkit.db import repo

    row = repo.tombstone_last_pick(conn, session["id"])
    if row is None:
        return None
    return Pick(**{**row, "is_mine": bool(row["is_mine"]), "undone": True})
