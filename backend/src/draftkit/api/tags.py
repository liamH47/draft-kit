"""Player tags: the user's own opinions, carried into every draft.

Tags are per-user, not per-league. They used to be keyed by league, which
meant every new draft started with an empty board and last week's targets
were stranded against a league id nobody would open again.

Every write is also mirrored to a JSON file beside the database. SQLite is
the source of truth; the file is the copy you can read, edit, back up, or
carry to another machine — and the thing that still has your cheat sheet if
the database is ever deleted.
"""

import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from draftkit.db import repo

router = APIRouter(prefix="/api/tags")

# The user's three-state board customization: take him early, take him at
# ADP, or let him fall well past it.
Tag = Literal["target", "at_adp", "fade"]


class TagUpdate(BaseModel):
    tag: Tag | None = None
    note: str | None = None


class TagImport(BaseModel):
    tags: dict[str, TagUpdate]


def mirror_path(request: Request):
    return request.app.state.settings.data_dir / "tags.json"


def write_mirror(request: Request) -> None:
    """Best-effort. A mirror that cannot be written must never cost the user
    the tag itself — the database already has it."""
    try:
        tags = repo.get_tags(request.app.state.db)
        payload = {
            player_id: {"tag": row["tag"], "note": row["note"], "updated_at": row["updated_at"]}
            for player_id, row in tags.items()
            if row["tag"] or row["note"]
        }
        path = mirror_path(request)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.part")
        tmp.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


@router.get("")
def list_tags(request: Request) -> dict[str, dict]:
    return repo.get_tags(request.app.state.db)


@router.put("/{player_id}")
def set_tag(request: Request, player_id: str, body: TagUpdate) -> dict:
    row = repo.set_tag(request.app.state.db, player_id, tag=body.tag, note=body.note)
    write_mirror(request)
    return row


@router.post("/import")
def import_tags(request: Request, body: TagImport) -> dict:
    """Merge a previously exported set back in. Absent players are left
    alone, so a partial file can only add opinions, never drop them."""
    written = repo.replace_tags(
        request.app.state.db,
        {pid: t.model_dump() for pid, t in body.tags.items()},
    )
    write_mirror(request)
    return {"imported": written, "tags": repo.get_tags(request.app.state.db)}


@router.post("/restore")
def restore_from_mirror(request: Request) -> dict:
    """Rebuild the tag table from the JSON file — the recovery path for a
    database that was deleted, moved, or started from the wrong directory."""
    path = mirror_path(request)
    if not path.is_file():
        raise HTTPException(404, f"no tag file at {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise HTTPException(422, f"{path} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(422, f"{path} does not hold a tag mapping")
    written = repo.replace_tags(request.app.state.db, payload)
    return {"restored": written, "tags": repo.get_tags(request.app.state.db)}
