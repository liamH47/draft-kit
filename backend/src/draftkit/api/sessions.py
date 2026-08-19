import asyncio
import json
import sqlite3

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from draftkit.db import repo
from draftkit.draft import ingest
from draftkit.engine.snake import picks_until_my_turn, round_and_slot

router = APIRouter(prefix="/api/sessions")


class SessionCreate(BaseModel):
    league_id: int
    name: str = "Draft"
    sync_source: str | None = None
    sync_ref: str | None = None


class PickCreate(BaseModel):
    player_id: str
    is_mine: bool | None = None
    source: str = "manual"


def _load(conn: sqlite3.Connection, session_id: int) -> tuple[dict, dict]:
    session = repo.get_session(conn, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    league = repo.get_league(conn, session["league_id"])
    if league is None:
        raise HTTPException(404, "league not found")
    return session, league


def _board(conn: sqlite3.Connection, session: dict, league: dict) -> dict:
    """Full resumable state: everything the board needs after a reload or a
    server restart is derived from the pick log, never from memory."""
    picks = repo.live_picks(conn, session["id"])
    num_teams = league["num_teams"]
    total = num_teams * league["rounds"]
    made = len(picks)
    on_clock = made + 1

    current = None
    if on_clock <= total:
        round_no, slot = round_and_slot(on_clock, num_teams)
        current = {"overall_no": on_clock, "round_no": round_no, "slot": slot}

    return {
        "session": session,
        "league": league,
        "picks": picks,
        "drafted_player_ids": [p["player_id"] for p in picks],
        "my_player_ids": [p["player_id"] for p in picks if p["is_mine"]],
        "on_the_clock": current,
        "picks_until_my_turn": picks_until_my_turn(
            num_teams, league["my_slot"], made, league["rounds"]
        ),
        "picks_made": made,
        "total_picks": total,
    }


@router.post("")
def create_session(request: Request, body: SessionCreate) -> dict:
    conn = request.app.state.db
    if repo.get_league(conn, body.league_id) is None:
        raise HTTPException(404, "league not found")
    session_id = repo.create_session(
        conn, body.league_id, body.name, sync_source=body.sync_source, sync_ref=body.sync_ref
    )
    session, league = _load(conn, session_id)
    return _board(conn, session, league)


@router.get("")
def list_sessions(request: Request) -> list[dict]:
    return repo.list_sessions(request.app.state.db)


@router.get("/{session_id}")
def get_session(request: Request, session_id: int) -> dict:
    conn = request.app.state.db
    session, league = _load(conn, session_id)
    return _board(conn, session, league)


@router.post("/{session_id}/picks")
def create_pick(request: Request, session_id: int, body: PickCreate) -> dict:
    conn = request.app.state.db
    session, league = _load(conn, session_id)
    try:
        pick = ingest.record_pick(
            conn, session, league, body.player_id, source=body.source, is_mine=body.is_mine
        )
    except ingest.DuplicatePick as exc:
        raise HTTPException(409, f"player {exc} is already drafted") from exc
    except ingest.DraftComplete as exc:
        raise HTTPException(409, str(exc)) from exc

    board = _board(conn, session, league)
    request.app.state.events.publish(
        session_id, "pick_recorded", {"pick": pick.model_dump(), "picks_made": board["picks_made"]}
    )
    return {"pick": pick.model_dump(), **board}


@router.post("/{session_id}/picks/undo")
def undo_pick(request: Request, session_id: int) -> dict:
    conn = request.app.state.db
    session, league = _load(conn, session_id)
    pick = ingest.undo_last_pick(conn, session)
    board = _board(conn, session, league)
    if pick is not None:
        request.app.state.events.publish(
            session_id,
            "pick_undone",
            {"pick": pick.model_dump(), "picks_made": board["picks_made"]},
        )
    return {"undone": pick.model_dump() if pick else None, **board}


@router.get("/{session_id}/events")
async def session_events(request: Request, session_id: int) -> StreamingResponse:
    conn = request.app.state.db
    _load(conn, session_id)
    bus = request.app.state.events
    queue = bus.subscribe(session_id)

    async def stream():
        try:
            yield "event: connected\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keepalive\n\n"  # keeps proxies from closing the stream
                    continue
                yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"
        finally:
            bus.unsubscribe(session_id, queue)

    return StreamingResponse(stream(), media_type="text/event-stream")
