from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Request

from draftkit.models.league import LeagueConfig, ScoringSettings
from draftkit.pool import build_pool
from draftkit.snapshots.store import SnapshotStore

router = APIRouter()

_OVERRIDES = Path(__file__).parent.parent / "identity" / "overrides.yaml"


@router.get("/api/players")
def players(
    request: Request,
    scoring: Literal["standard", "half_ppr", "ppr"] = "half_ppr",
    teams: int = 12,
) -> dict[str, object]:
    settings = request.app.state.settings
    store: SnapshotStore = request.app.state.snapshot_store
    league = LeagueConfig(scoring=ScoringSettings.preset(scoring), num_teams=teams)
    result = build_pool(
        store,
        league,
        season=settings.season,
        scoring_preset=scoring,
        overrides_path=_OVERRIDES,
    )
    return {
        "players": [p.model_dump() for p in result.players],
        "sources": {
            name: {
                "fetched_at": meta.fetched_at.isoformat(),
                "stale": meta.stale,
                "from_cache": meta.from_cache,
            }
            for name, meta in result.sources.items()
        },
        "unmatched_count": len(result.unmatched),
    }
