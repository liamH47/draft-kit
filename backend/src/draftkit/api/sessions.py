import asyncio
import json
import sqlite3

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from draftkit.auth.routes import CurrentUser
from draftkit.board import build_board
from draftkit.db import repo
from draftkit.draft import ingest
from draftkit.engine.snake import picks_until_my_turn, round_and_slot

router = APIRouter(prefix="/api/sessions")

# How long the SSE stream waits before emitting a comment line. Proxies drop
# idle connections, and a draft can sit quiet while someone deliberates.
KEEPALIVE_SECONDS = 15.0


class SessionCreate(BaseModel):
    league_id: int
    name: str = "Draft"
    sync_source: str | None = None
    sync_ref: str | None = None


class PickCreate(BaseModel):
    player_id: str
    is_mine: bool | None = None
    source: str = "manual"


def _load(conn: sqlite3.Connection, session_id: int, user_id: str) -> tuple[dict, dict]:
    """Every session route funnels through here, so ownership is enforced
    once. Somebody else's session id answers 404, the same as an id that
    never existed - a guessed URL learns nothing."""
    session = repo.get_session(conn, session_id, user_id)
    if session is None:
        raise HTTPException(404, "session not found")
    league = repo.get_league(conn, session["league_id"], user_id)
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
def create_session(request: Request, body: SessionCreate, user: CurrentUser) -> dict:
    conn = request.app.state.db
    if repo.get_league(conn, body.league_id, user.user_id) is None:
        raise HTTPException(404, "league not found")
    session_id = repo.create_session(
        conn,
        body.league_id,
        body.name,
        sync_source=body.sync_source,
        sync_ref=body.sync_ref,
        user_id=user.user_id,
    )
    session, league = _load(conn, session_id, user.user_id)
    return _board(conn, session, league)


@router.get("")
def list_sessions(request: Request, user: CurrentUser) -> list[dict]:
    return repo.list_sessions(request.app.state.db, user.user_id)


@router.get("/{session_id}")
def get_session(request: Request, session_id: int, user: CurrentUser) -> dict:
    conn = request.app.state.db
    session, league = _load(conn, session_id, user.user_id)
    return _board(conn, session, league)


@router.get("/{session_id}/board")
def get_board(request: Request, session_id: int, user: CurrentUser) -> dict:
    """Everything the draft screen needs in one request."""
    conn = request.app.state.db
    session, league = _load(conn, session_id, user.user_id)
    return build_board(
        conn,
        request.app.state.snapshot_store,
        session,
        league,
        season=request.app.state.settings.season,
    )


@router.post("/{session_id}/picks")
def create_pick(request: Request, session_id: int, body: PickCreate, user: CurrentUser) -> dict:
    conn = request.app.state.db
    session, league = _load(conn, session_id, user.user_id)
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


class PickCorrection(BaseModel):
    player_id: str


@router.put("/{session_id}/picks/{overall_no}")
def correct_pick(
    request: Request, session_id: int, overall_no: int, body: PickCorrection, user: CurrentUser
) -> dict:
    """Fix a pick you got wrong several picks ago, without unwinding the board."""
    conn = request.app.state.db
    session, league = _load(conn, session_id, user.user_id)
    try:
        pick = ingest.correct_pick(conn, session, league, overall_no, body.player_id)
    except ingest.NoSuchPick as exc:
        raise HTTPException(404, str(exc)) from exc
    except ingest.DuplicatePick as exc:
        raise HTTPException(409, f"player {exc} is already drafted") from exc

    board = _board(conn, session, league)
    request.app.state.events.publish(session_id, "pick_corrected", {"pick": pick.model_dump()})
    return {"pick": pick.model_dump(), **board}


@router.post("/{session_id}/picks/undo")
def undo_pick(request: Request, session_id: int, user: CurrentUser) -> dict:
    conn = request.app.state.db
    session, league = _load(conn, session_id, user.user_id)
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
async def session_events(request: Request, session_id: int, user: CurrentUser) -> StreamingResponse:
    conn = request.app.state.db
    _load(conn, session_id, user.user_id)
    bus = request.app.state.events
    queue = bus.subscribe(session_id)

    async def stream():
        # No explicit disconnect polling: when the client goes away the server
        # closes this generator, so the finally below is what cleans up. Polling
        # request.is_disconnected() inside the loop can block on a receive that
        # never arrives and stall the stream instead.
        try:
            yield "event: connected\ndata: {}\n\n"
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), KEEPALIVE_SECONDS)
                except TimeoutError:
                    yield ": keepalive\n\n"  # stops proxies closing an idle stream
                    continue
                yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"
        finally:
            bus.unsubscribe(session_id, queue)

    return StreamingResponse(stream(), media_type="text/event-stream")
