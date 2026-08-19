from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from draftkit.api import health, leagues, players, sessions, tags
from draftkit.config import Settings, get_settings
from draftkit.db.connection import connect, migrate
from draftkit.draft.events import EventBus
from draftkit.snapshots.store import SnapshotStore


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="draftkit")
    app.state.settings = settings
    app.state.snapshot_store = SnapshotStore(settings.snapshots_dir)
    app.state.db = connect(settings.db_path)
    migrate(app.state.db)
    app.state.events = EventBus()

    for router in (health, players, leagues, sessions, tags):
        app.include_router(router.router)

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
