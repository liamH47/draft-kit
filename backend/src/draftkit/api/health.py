from fastapi import APIRouter, Request

from draftkit import __version__

router = APIRouter()


@router.get("/api/health")
def health(request: Request) -> dict[str, object]:
    return {
        "status": "ok",
        "version": __version__,
        # Hours since the newest snapshot per source — check this the morning
        # of a draft.
        "snapshots": request.app.state.snapshot_store.ages(),
    }
