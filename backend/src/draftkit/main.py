from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from draftkit.api import health, players
from draftkit.config import Settings, get_settings
from draftkit.snapshots.store import SnapshotStore


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="draftkit")
    app.state.settings = settings
    app.state.snapshot_store = SnapshotStore(settings.snapshots_dir)
    app.include_router(health.router)
    app.include_router(players.router)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    if settings.static_dir is not None:
        # Prod: serve the built frontend from the same origin as the API.
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="static")

    return app


app = create_app()
