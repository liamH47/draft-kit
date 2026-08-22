"""The draft board: the scored pool minus who's gone, plus advice.

This is the one read the UI makes during a draft, so it assembles everything
in one pass — remaining players with VORP and your tags attached, and the
recommendations that follow from them.
"""

import sqlite3
from pathlib import Path
from typing import Any

from draftkit.db import repo
from draftkit.engine.availability import vona
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
    tags = repo.get_tags(conn)

    drafted = {p["player_id"] for p in picks}
    mine = [p["player_id"] for p in picks if p["is_mine"]]

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

    # The pick this advice is for, and the one after it — the gap between them
    # is what "waiting" actually costs, and it is the whole input to scarcity.
    my_pick = on_clock if until_turn is None else on_clock + until_turn
    my_round = round_and_slot(min(my_pick, total), num_teams)[0]
    next_pick = (
        my_pick + gap_after(my_round, config.my_slot, num_teams) if my_round < rounds else None
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
    by_position: dict[str, list[Any]] = {}

    for player in pool_result.players:
        tag_row = tags.get(player.player_id, {})
        row = player.model_dump() | {
            "tag": tag_row.get("tag"),
            "note": tag_row.get("note"),
            # Picks he has lasted PAST his market price: positive is a bargain
            # (still here after the room usually takes him), negative is a
            # reach. The column header promises that sign, and the score's ADP
            # term already uses it — this read the other way round, so the
            # board's biggest bargain was painted red as a reach.
            "adp_delta": (round(on_clock - player.adp, 1) if player.adp is not None else None),
        }
        if player.player_id in drafted:
            drafted_rows[player.player_id] = row
            if player.player_id in mine:
                my_counts[player.position] = my_counts.get(player.position, 0) + 1
                my_players.append(row)
            continue
        available.append(row)
        by_position.setdefault(player.position, []).append(player)
        candidates.append(
            Candidate(
                player_id=player.player_id,
                name=player.name,
                position=player.position,
                points=player.points,
                # The score's backbone is the VOLS/VORP midpoint, so a
                # projection tail that craters at one position can't skew
                # cross-position value.
                vorp=player.value,
                adp=player.adp,
                tier=(player.tier_expert if player.position in expert_positions else player.tier),
                tag=tag_row.get("tag"),
                list_vs_market=player.list_vs_market,
            )
        )

    # Second pass: VONA compares a player against everyone still available at
    # his position, so it cannot be computed until the first pass has seen
    # them all.
    vona_by_id: dict[str, float] = {}
    if next_pick is not None:
        for players in by_position.values():
            field = [(p.value, p.adp, p.adp_stdev) for p in players]
            for i, player in enumerate(players):
                others = field[:i] + field[i + 1 :]
                vona_by_id[player.player_id] = round(vona(player.value, others, next_pick), 1)
        for row in available:
            row["vona"] = vona_by_id.get(row["player_id"])
        for candidate in candidates:
            candidate.vona = vona_by_id.get(candidate.player_id)

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
