from fastapi import APIRouter

from draftkit import __version__

router = APIRouter()


@router.get("/api/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "version": __version__,
        # Filled in at M1: per-source snapshot ages so you can check data
        # freshness the morning of a draft.
        "snapshots": {},
    }
