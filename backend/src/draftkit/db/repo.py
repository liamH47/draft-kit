"""Thin data-access layer. No business logic — that lives in draft/ and engine/."""

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from draftkit.models.league import LeagueConfig


def _now() -> str:
    return datetime.now(UTC).isoformat()


# --- leagues ---------------------------------------------------------------


def create_league(
    conn: sqlite3.Connection,
    config: LeagueConfig,
    *,
    scoring_preset: str,
    rounds: int = 15,
    user_id: str = "local",
) -> int:
    with conn:
        cur = conn.execute(
            """INSERT INTO league
               (user_id, name, platform, num_teams, my_slot, rounds, scoring_preset,
                config_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                config.name,
                config.platform,
                config.num_teams,
                config.my_slot,
                rounds,
                scoring_preset,
                config.model_dump_json(),
                _now(),
            ),
        )
    return int(cur.lastrowid or 0)


def get_league(conn: sqlite3.Connection, league_id: int, user_id: str = "local") -> dict | None:
    row = conn.execute(
        "SELECT * FROM league WHERE id = ? AND user_id = ?", (league_id, user_id)
    ).fetchone()
    return _league_row(row) if row else None


def list_leagues(conn: sqlite3.Connection, user_id: str = "local") -> list[dict]:
    rows = conn.execute("SELECT * FROM league WHERE user_id = ? ORDER BY id", (user_id,)).fetchall()
    return [_league_row(r) for r in rows]


def _league_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["config"] = json.loads(data.pop("config_json"))
    return data


# --- sessions --------------------------------------------------------------


def create_session(
    conn: sqlite3.Connection,
    league_id: int,
    name: str,
    *,
    sync_source: str | None = None,
    sync_ref: str | None = None,
    user_id: str = "local",
) -> int:
    with conn:
        cur = conn.execute(
            """INSERT INTO draft_session
               (user_id, league_id, name, sync_source, sync_ref, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, league_id, name, sync_source, sync_ref, _now()),
        )
    return int(cur.lastrowid or 0)


def get_session(conn: sqlite3.Connection, session_id: int, user_id: str = "local") -> dict | None:
    row = conn.execute(
        "SELECT * FROM draft_session WHERE id = ? AND user_id = ?", (session_id, user_id)
    ).fetchone()
    return dict(row) if row else None


def list_sessions(conn: sqlite3.Connection, user_id: str = "local") -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM draft_session WHERE user_id = ? ORDER BY id DESC", (user_id,)
    ).fetchall()
    return [dict(r) for r in rows]


# --- picks -----------------------------------------------------------------


def live_picks(conn: sqlite3.Connection, session_id: int) -> list[dict]:
    """Picks that still stand, in draft order (tombstoned ones excluded)."""
    rows = conn.execute(
        "SELECT * FROM pick WHERE session_id = ? AND undone = 0 ORDER BY overall_no",
        (session_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def append_pick(conn: sqlite3.Connection, session_id: int, pick: dict[str, Any]) -> dict:
    with conn:
        seq = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS next FROM pick WHERE session_id = ?",
            (session_id,),
        ).fetchone()["next"]
        cur = conn.execute(
            """INSERT INTO pick
               (session_id, seq, overall_no, round_no, slot, player_id, is_mine, source,
                created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                seq,
                pick["overall_no"],
                pick["round_no"],
                pick["slot"],
                pick["player_id"],
                int(pick.get("is_mine", False)),
                pick.get("source", "manual"),
                _now(),
            ),
        )
    row = conn.execute("SELECT * FROM pick WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


def tombstone_pick_at(conn: sqlite3.Connection, session_id: int, overall_no: int) -> dict | None:
    """Retire one specific pick, leaving its slot free to be refilled."""
    row = conn.execute(
        "SELECT * FROM pick WHERE session_id = ? AND overall_no = ? AND undone = 0",
        (session_id, overall_no),
    ).fetchone()
    if row is None:
        return None
    with conn:
        conn.execute("UPDATE pick SET undone = 1 WHERE id = ?", (row["id"],))
    return dict(row)


def tombstone_last_pick(conn: sqlite3.Connection, session_id: int) -> dict | None:
    """Undo: flag the highest live pick as undone. The row stays for the audit
    trail so a later live-sync disagreement is visible rather than silent."""
    row = conn.execute(
        """SELECT * FROM pick WHERE session_id = ? AND undone = 0
           ORDER BY overall_no DESC LIMIT 1""",
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    with conn:
        conn.execute("UPDATE pick SET undone = 1 WHERE id = ?", (row["id"],))
    return dict(row)


# --- tags / notes ----------------------------------------------------------


def set_tag(
    conn: sqlite3.Connection,
    league_id: int,
    player_id: str,
    *,
    tag: str | None,
    note: str | None,
    user_id: str = "local",
) -> dict:
    with conn:
        conn.execute(
            """INSERT INTO player_tag (user_id, league_id, player_id, tag, note, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id, league_id, player_id) DO UPDATE SET
                 tag = excluded.tag, note = excluded.note, updated_at = excluded.updated_at""",
            (user_id, league_id, player_id, tag, note, _now()),
        )
    row = conn.execute(
        "SELECT * FROM player_tag WHERE user_id = ? AND league_id = ? AND player_id = ?",
        (user_id, league_id, player_id),
    ).fetchone()
    return dict(row)


def get_tags(conn: sqlite3.Connection, league_id: int, user_id: str = "local") -> dict[str, dict]:
    rows = conn.execute(
        "SELECT * FROM player_tag WHERE user_id = ? AND league_id = ?", (user_id, league_id)
    ).fetchall()
    return {r["player_id"]: dict(r) for r in rows}
