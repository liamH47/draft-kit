from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from draftkit.api import health, leagues, players, rankings, sessions, tags
from draftkit.config import Settings, get_settings
from draftkit.db.connection import connect, migrate
from draftkit.draft.events import EventBus
from draftkit.snapshots.store import SnapshotStore


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="draftkit")
    app.state.settings = settings
    app.state.snapshot_store = SnapshotStore(settings.snapshots_dir, offline=settings.offline)
    app.state.db = connect(settings.db_path)
    migrate(app.state.db)
    app.state.events = EventBus()

    for router in (health, players, leagues, rankings, sessions, tags):
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
        static_dir = settings.static_dir
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

        @app.get("/{path:path}")
        def spa(path: str) -> FileResponse:
            """Client-side routing: deep links like /draft/3 must serve the
            app shell rather than 404, but real files still win."""
            candidate = (static_dir / path).resolve()
            if path and candidate.is_file() and candidate.is_relative_to(static_dir.resolve()):
                return FileResponse(candidate)
            index = static_dir / "index.html"
            if not index.is_file():
                raise HTTPException(404, "frontend not built")
            return FileResponse(index)

    return app


app = create_app()
