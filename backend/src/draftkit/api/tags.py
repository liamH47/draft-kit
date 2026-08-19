from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from draftkit.db import repo

router = APIRouter(prefix="/api/leagues/{league_id}/tags")

# The user's three-state board customization: take him early, take him at
# ADP, or let him fall well past it.
Tag = Literal["target", "at_adp", "fade"]


class TagUpdate(BaseModel):
    tag: Tag | None = None
    note: str | None = None


@router.get("")
def list_tags(request: Request, league_id: int) -> dict[str, dict]:
    conn = request.app.state.db
    if repo.get_league(conn, league_id) is None:
        raise HTTPException(404, "league not found")
    return repo.get_tags(conn, league_id)


@router.put("/{player_id}")
def set_tag(request: Request, league_id: int, player_id: str, body: TagUpdate) -> dict:
    conn = request.app.state.db
    if repo.get_league(conn, league_id) is None:
        raise HTTPException(404, "league not found")
    return repo.set_tag(conn, league_id, player_id, tag=body.tag, note=body.note)
