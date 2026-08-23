"""Thin data-access layer. No business logic — that lives in draft/ and engine/."""

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from draftkit.models.league import LeagueConfig


def _now() -> str:
    return datetime.now(UTC).isoformat()


# --- users ------------------------------------------------------------------


def upsert_user(
    conn: sqlite3.Connection, *, google_sub: str, email: str, name: str, picture: str
) -> dict:
    """One row per Google identity that has signed in. Authorization is the
    env allow-list, not this table — it exists for display and for answering
    "who has actually used this install"."""
    now = _now()
    with conn:
        conn.execute(
            """INSERT INTO user_account (google_sub, email, name, picture, first_login, last_login)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(google_sub) DO UPDATE SET
                 email = excluded.email, name = excluded.name, picture = excluded.picture,
                 last_login = excluded.last_login""",
            (google_sub, email, name, picture, now, now),
        )
    row = conn.execute("SELECT * FROM user_account WHERE google_sub = ?", (google_sub,)).fetchone()
    return dict(row)


# --- leagues ---------------------------------------------------------------


def create_league(
    conn: sqlite3.Connection,
    config: LeagueConfig,
    *,
    scoring_preset: str,
    rounds: int = 15,
    user_id: str,
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


def get_league(conn: sqlite3.Connection, league_id: int, user_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM league WHERE id = ? AND user_id = ?", (league_id, user_id)
    ).fetchone()
    return _league_row(row) if row else None


def list_leagues(conn: sqlite3.Connection, user_id: str) -> list[dict]:
    rows = conn.execute("SELECT * FROM league WHERE user_id = ? ORDER BY id", (user_id,)).fetchall()
    return [_league_row(r) for r in rows]


def league_team_counts(conn: sqlite3.Connection) -> set[int]:
    """Every league's team count, across ALL users on purpose: snapshot
    warming is per shape, not per user, and a warm run that skipped a
    friend's 8-team league would leave their offline draft unreadable."""
    rows = conn.execute("SELECT DISTINCT num_teams FROM league").fetchall()
    return {row["num_teams"] for row in rows}


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
    user_id: str,
) -> int:
    with conn:
        cur = conn.execute(
            """INSERT INTO draft_session
               (user_id, league_id, name, sync_source, sync_ref, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, league_id, name, sync_source, sync_ref, _now()),
        )
    return int(cur.lastrowid or 0)


def get_session(conn: sqlite3.Connection, session_id: int, user_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM draft_session WHERE id = ? AND user_id = ?", (session_id, user_id)
    ).fetchone()
    return dict(row) if row else None


def list_sessions(conn: sqlite3.Connection, user_id: str) -> list[dict]:
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
    player_id: str,
    *,
    tag: str | None,
    note: str | None,
    user_id: str,
) -> dict:
    """Tags are per-user, not per-league: they are opinions about players and
    they follow you into every draft you run."""
    with conn:
        conn.execute(
            """INSERT INTO player_tag (user_id, player_id, tag, note, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(user_id, player_id) DO UPDATE SET
                 tag = excluded.tag, note = excluded.note, updated_at = excluded.updated_at""",
            (user_id, player_id, tag, note, _now()),
        )
    row = conn.execute(
        "SELECT * FROM player_tag WHERE user_id = ? AND player_id = ?",
        (user_id, player_id),
    ).fetchone()
    return dict(row)


def get_tags(conn: sqlite3.Connection, user_id: str) -> dict[str, dict]:
    rows = conn.execute("SELECT * FROM player_tag WHERE user_id = ?", (user_id,)).fetchall()
    return {r["player_id"]: dict(r) for r in rows}


def replace_tags(conn: sqlite3.Connection, tags: dict[str, dict], *, user_id: str) -> int:
    """Merge an exported tag set back in (import). Rows already present are
    overwritten; rows absent from the import are left alone, so importing a
    partial file can only add opinions, never silently drop them."""
    written = 0
    with conn:
        for player_id, row in tags.items():
            tag = row.get("tag") if isinstance(row, dict) else row
            if tag not in ("target", "at_adp", "fade", None):
                continue
            conn.execute(
                """INSERT INTO player_tag (user_id, player_id, tag, note, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(user_id, player_id) DO UPDATE SET
                     tag = excluded.tag, note = excluded.note,
                     updated_at = excluded.updated_at""",
                (
                    user_id,
                    str(player_id),
                    tag,
                    (row.get("note") if isinstance(row, dict) else None),
                    _now(),
                ),
            )
            written += 1
    return written


# --- custom ranking lists --------------------------------------------------


def replace_ranking_list(
    conn: sqlite3.Connection,
    list_name: str,
    rows: list[dict[str, Any]],
    *,
    user_id: str,
) -> int:
    """Store a pasted list, replacing any previous paste under that name.

    Wholesale replacement rather than a merge: re-pasting a list means the
    publisher updated it, and a merge would leave last week's players sitting
    at ranks the new list no longer has.
    """
    now = _now()
    with conn:
        conn.execute(
            "DELETE FROM custom_ranking WHERE user_id = ? AND list_name = ?",
            (user_id, list_name),
        )
        conn.executemany(
            """INSERT INTO custom_ranking
                 (user_id, list_name, rank, player_id, source_name, position, team, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    user_id,
                    list_name,
                    row["rank"],
                    row.get("player_id"),
                    row["source_name"],
                    row.get("position"),
                    row.get("team"),
                    now,
                )
                for row in rows
            ],
        )
    return len(rows)


def get_ranking_list(conn: sqlite3.Connection, list_name: str, *, user_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM custom_ranking WHERE user_id = ? AND list_name = ? ORDER BY rank",
        (user_id, list_name),
    ).fetchall()
    return [dict(r) for r in rows]


def get_ranking_lists(conn: sqlite3.Connection, user_id: str) -> dict[str, list[dict]]:
    """Every list the user holds, keyed by name. This is what the pool joins
    against, so it returns rows rather than counts."""
    rows = conn.execute(
        "SELECT * FROM custom_ranking WHERE user_id = ? ORDER BY list_name, rank",
        (user_id,),
    ).fetchall()
    lists: dict[str, list[dict]] = {}
    for row in rows:
        lists.setdefault(row["list_name"], []).append(dict(row))
    return lists


def ranking_list_summaries(conn: sqlite3.Connection, user_id: str) -> list[dict]:
    """Name, size and how much of it resolved — the numbers the UI shows so a
    list that half failed to match is obvious before draft night."""
    rows = conn.execute(
        """SELECT list_name,
                  COUNT(*) AS total,
                  COUNT(player_id) AS matched,
                  MAX(updated_at) AS updated_at
           FROM custom_ranking WHERE user_id = ?
           GROUP BY list_name ORDER BY list_name""",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def custom_ranks_for_pool(conn: sqlite3.Connection, user_id: str) -> dict[str, dict[str, float]]:
    """Shaped the way the pool wants it: list name -> player id -> rank.

    Rows whose name never resolved are dropped here rather than earlier — they
    are kept in the table so the user can see what failed, but the pool has
    nothing to join them to.
    """
    out: dict[str, dict[str, float]] = {}
    for list_name, rows in get_ranking_lists(conn, user_id).items():
        ranks = {r["player_id"]: float(r["rank"]) for r in rows if r["player_id"]}
        if ranks:
            out[list_name] = ranks
    return out


def delete_ranking_list(conn: sqlite3.Connection, list_name: str, *, user_id: str) -> int:
    with conn:
        cur = conn.execute(
            "DELETE FROM custom_ranking WHERE user_id = ? AND list_name = ?",
            (user_id, list_name),
        )
    return cur.rowcount
