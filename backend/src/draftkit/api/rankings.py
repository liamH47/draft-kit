"""Bring-your-own ranking lists: paste a cheat sheet, get a column.

The published lists this app fetches (ESPN, CBS, Boris Chen) are the ones that
are free to fetch. The good ones people actually pay for are not, and scraping
a paywall is not on. So the user brings them by hand: copy a PDF cheat sheet, a
spreadsheet column, or a table selected off a page, and paste it here.

An imported list joins the published ones on equal terms — it feeds the
consensus rank shown on the board and the small list-vs-market nudge in the
score. It never becomes a projection: a ranking says who people take, and the
projections say who is good, and mixing those two would count one opinion
twice.

Every write is mirrored to a JSON file beside the database, on the same terms
as tags: SQLite is the truth, the file is the copy you can read, back up, or
carry to another machine.
"""

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from draftkit.db import repo
from draftkit.identity.ranklist import parse_ranking_text
from draftkit.identity.resolver import Resolver
from draftkit.models.player import FANTASY_POSITIONS
from draftkit.pool import clear_pool_cache
from draftkit.snapshots.store import SnapshotStore
from draftkit.sources import dp_playerids, sleeper_players

router = APIRouter(prefix="/api/rankings")

_OVERRIDES = Path(__file__).parent.parent / "identity" / "overrides.yaml"

# A list name becomes part of a source key on every player row, so keep it to
# something that reads cleanly in a tooltip and cannot collide with a feed.
_NAME_OK = re.compile(r"^[\w][\w .-]{0,39}$")


class RankingPaste(BaseModel):
    text: str = Field(min_length=1)


def mirror_path(request: Request) -> Path:
    return request.app.state.settings.data_dir / "rankings.json"


def write_mirror(request: Request) -> None:
    """Best effort, exactly as for tags: a mirror that will not write must
    never cost the user the list, which the database already holds."""
    try:
        payload = repo.get_ranking_lists(request.app.state.db)
        path = mirror_path(request)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.part")
        tmp.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def _resolver(request: Request) -> Resolver:
    """Build the same name resolver the pool uses, so a list resolves against
    exactly the player universe the board will be built from."""
    store: SnapshotStore = request.app.state.snapshot_store
    players_ds, _ = store.get(sleeper_players)
    crosswalk = []
    try:
        dp_ds, _ = store.get(dp_playerids)
        crosswalk = dp_ds.rows
    except Exception:
        pass
    return Resolver.build(players_ds.rows, crosswalk, _OVERRIDES)


def _resolve(resolver: Resolver, name: str, position: str | None, team: str | None) -> str | None:
    """Resolve a pasted name, working around the fact that a cheat sheet may
    not have said which position he plays.

    With a position it is the ordinary lookup. Without one, every position is
    tried and the answer is accepted only if exactly one of them matches —
    two players sharing a name across positions is precisely the case where a
    guess would put the wrong man on the board.
    """
    if position:
        return resolver.resolve(name, position, team).sleeper_id
    hits = {
        resolved
        for pos in FANTASY_POSITIONS
        if (resolved := resolver.resolve(name, pos, team).sleeper_id)
    }
    return hits.pop() if len(hits) == 1 else None


@router.get("")
def list_rankings(request: Request) -> dict[str, list[dict]]:
    """Name, size and match rate per list — enough for the UI to show that a
    list half failed to resolve, well before draft night."""
    return {"lists": repo.ranking_list_summaries(request.app.state.db)}


@router.get("/{list_name}")
def get_ranking(request: Request, list_name: str) -> dict:
    rows = repo.get_ranking_list(request.app.state.db, list_name)
    if not rows:
        raise HTTPException(404, f"no ranking list called {list_name!r}")
    return {"name": list_name, "rows": rows}


@router.put("/{list_name}")
def import_ranking(request: Request, list_name: str, body: RankingPaste) -> dict:
    """Parse a pasted list, resolve what it names, and store the lot.

    Names that did not resolve are stored too, with no player id, and returned
    so the user can see them. A list that silently came up fourteen players
    short is the failure that gets discovered in round four.
    """
    if not _NAME_OK.match(list_name):
        raise HTTPException(422, "list name must be 1-40 letters, digits, spaces, dots or dashes")
    parsed = parse_ranking_text(body.text)
    if not parsed:
        raise HTTPException(422, "no player names found in that text")

    resolver = _resolver(request)
    rows = []
    unmatched = []
    for entry in parsed:
        player_id = _resolve(resolver, entry.name, entry.position, entry.team)
        if player_id is None:
            unmatched.append(entry.name)
        rows.append(
            {
                "rank": entry.rank,
                "player_id": player_id,
                "source_name": entry.name,
                "position": entry.position,
                "team": entry.team,
            }
        )
    repo.replace_ranking_list(request.app.state.db, list_name, rows)
    write_mirror(request)
    # The pool caches per configuration, and this list is part of that
    # configuration — without this the board would show yesterday's consensus.
    clear_pool_cache()
    return {
        "name": list_name,
        "total": len(rows),
        "matched": len(rows) - len(unmatched),
        "unmatched": unmatched,
    }


@router.delete("/{list_name}")
def delete_ranking(request: Request, list_name: str) -> dict:
    removed = repo.delete_ranking_list(request.app.state.db, list_name)
    if not removed:
        raise HTTPException(404, f"no ranking list called {list_name!r}")
    write_mirror(request)
    clear_pool_cache()
    return {"name": list_name, "removed": removed}


@router.post("/restore")
def restore_from_mirror(request: Request) -> dict:
    """Rebuild the tables from the JSON file — the recovery path for a database
    that was deleted, moved, or started from the wrong directory."""
    path = mirror_path(request)
    if not path.is_file():
        raise HTTPException(404, f"no ranking file at {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise HTTPException(422, f"{path} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(422, f"{path} does not hold ranking lists")
    restored = 0
    for list_name, rows in payload.items():
        restored += repo.replace_ranking_list(request.app.state.db, str(list_name), rows)
    clear_pool_cache()
    return {"restored": restored, "lists": repo.ranking_list_summaries(request.app.state.db)}
