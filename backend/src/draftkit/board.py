"""The draft board: the scored pool minus who's gone, plus advice.

This is the one read the UI makes during a draft, so it assembles everything
in one pass — remaining players with VORP and your tags attached, and the
recommendations that follow from them.
"""

import sqlite3
from pathlib import Path
from typing import Any

from draftkit.db import repo
from draftkit.engine.baselines import baselines
from draftkit.engine.recommend import Candidate, recommend
from draftkit.engine.snake import gap_after, picks_until_my_turn, round_and_slot
from draftkit.models.league import LeagueConfig
from draftkit.pool import build_pool_cached
from draftkit.snapshots.store import SnapshotStore

_OVERRIDES = Path(__file__).parent / "identity" / "overrides.yaml"


def build_board(
    conn: sqlite3.Connection,
    store: SnapshotStore,
    session: dict,
    league_row: dict,
    *,
    season: int,
    rec_limit: int = 5,
) -> dict[str, Any]:
    config = LeagueConfig(**league_row["config"])
    scoring_preset = league_row["scoring_preset"]
    num_teams = league_row["num_teams"]
    rounds = league_row["rounds"]

    pool_result = build_pool_cached(
        store,
        config,
        season=season,
        scoring_preset=scoring_preset,
        overrides_path=_OVERRIDES,
    )
    picks = repo.live_picks(conn, session["id"])
    tags = repo.get_tags(conn, league_row["id"])

    drafted = {p["player_id"] for p in picks}
    mine = [p["player_id"] for p in picks if p["is_mine"]]

    # Baselines come from the FULL pool: replacement level is a property of
    # the player universe, not of who happens to be left on the board.
    points_by_position: dict[str, list[float]] = {}
    for player in pool_result.players:
        points_by_position.setdefault(player.position, []).append(player.points)
    bases = baselines(config, points_by_position)

    made = len(picks)
    on_clock = made + 1
    total = num_teams * rounds
    until_turn = picks_until_my_turn(num_teams, config.my_slot, made, rounds)
    # On my own pick until_turn is 0, which would silence tier urgency at the
    # only moment recommendations matter. Urgency there is about surviving to
    # my NEXT turn, so hand recommend() that gap instead (None in the final
    # round — there is no next turn). The UI keeps the raw 0: it means "you're
    # on the clock".
    rec_until = until_turn
    if until_turn == 0:
        my_round = round_and_slot(made + 1, num_teams)[0]
        rec_until = (
            gap_after(my_round, config.my_slot, num_teams) - 1 if my_round < rounds else None
        )

    available: list[dict[str, Any]] = []
    candidates: list[Candidate] = []
    my_counts: dict[str, int] = {}
    my_players: list[dict[str, Any]] = []
    drafted_rows: dict[str, dict[str, Any]] = {}

    # Urgency needs tiers that mean scarcity. Gap tiers on the flat live WR
    # curve run 18-70 players wide (firing for everyone but WRs), while Boris
    # Chen's expert tiers have sane sizes — so prefer expert tiers wherever he
    # covers the position, gap tiers only where he doesn't (K, most DEF).
    # Numbering must never mix within a position: an uncovered player at a
    # covered position gets no tier rather than a colliding gap tier.
    expert_positions = {p.position for p in pool_result.players if p.tier_expert}

    for player in pool_result.players:
        base = bases.get(player.position, {"vorp": 0.0, "vols": 0.0, "value": 0.0})
        vorp = round(player.points - base["vorp"], 1)
        vols = round(player.points - base["vols"], 1)
        # What the score is built on: the VOLS/VORP midpoint, so a projection
        # tail that craters at one position can't skew cross-position value.
        value = round(player.points - base["value"], 1)
        tag_row = tags.get(player.player_id, {})
        row = player.model_dump() | {
            "vorp": vorp,
            "vols": vols,
            "tag": tag_row.get("tag"),
            "note": tag_row.get("note"),
            "adp_delta": (round(player.adp - on_clock, 1) if player.adp is not None else None),
        }
        if player.player_id in drafted:
            drafted_rows[player.player_id] = row
            if player.player_id in mine:
                my_counts[player.position] = my_counts.get(player.position, 0) + 1
                my_players.append(row)
            continue
        available.append(row)
        candidates.append(
            Candidate(
                player_id=player.player_id,
                name=player.name,
                position=player.position,
                points=player.points,
                vorp=value,
                adp=player.adp,
                tier=(player.tier_expert if player.position in expert_positions else player.tier),
                tag=tag_row.get("tag"),
                list_vs_market=player.list_vs_market,
            )
        )

    recommendations = (
        recommend(
            candidates,
            league=config,
            my_counts=my_counts,
            current_pick=on_clock,
            picks_until_turn=rec_until,
            current_round=round_and_slot(min(on_clock, total), num_teams)[0],
            total_rounds=rounds,
            autodraft_count=config.autodraft_count,
            limit=rec_limit,
        )
        if on_clock <= total
        else []
    )

    current = None
    if on_clock <= total:
        round_no, slot = round_and_slot(on_clock, num_teams)
        current = {"overall_no": on_clock, "round_no": round_no, "slot": slot}

    return {
        "session": session,
        "league": league_row,
        "available": available,
        "recommendations": [r.__dict__ for r in recommendations],
        "my_players": my_players,
        "my_counts": my_counts,
        # Who is off the board, with names — so the pick log reads as names and
        # a search for someone already taken can say so instead of coming back
        # empty, which is indistinguishable from a typo mid-draft.
        "drafted": [
            {
                **drafted_rows.get(p["player_id"], {"player_id": p["player_id"], "name": "?"}),
                "overall_no": p["overall_no"],
                "round_no": p["round_no"],
                "is_mine": bool(p["is_mine"]),
            }
            for p in picks
        ],
        "picks": picks,
        "on_the_clock": current,
        "picks_until_my_turn": until_turn,
        "picks_made": made,
        "total_picks": total,
        "sources": {
            name: {
                "fetched_at": meta.fetched_at.isoformat(),
                "stale": meta.stale,
            }
            for name, meta in pool_result.sources.items()
        },
    }
