"""Paths that only run when something goes wrong, or when the app is deployed.

These are the branches a happy-path suite never touches: 404s, degraded data
sources, the SSE stream, the production static-file mount, and the one function
that actually talks to the network.
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import cast

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from draftkit.api.sessions import session_events
from draftkit.auth.session import SessionUser
from draftkit.config import Settings
from draftkit.db import repo
from draftkit.db.connection import connect, migrate
from draftkit.engine.adp import blend_adp
from draftkit.engine.recommend import Candidate, recommend
from draftkit.main import create_app
from draftkit.models.league import LeagueConfig, RosterSlots, ScoringSettings
from draftkit.pool import build_pool
from draftkit.snapshots.store import SnapshotStore, http_fetch
from draftkit.sources.base import RawPayload, RequestSpec

# --- missing resources ------------------------------------------------------


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(Settings(data_dir=tmp_path / "data")))


def test_unknown_ids_are_404s_not_500s(client):
    assert client.get("/api/leagues/999").status_code == 404
    assert client.get("/api/sessions/999").status_code == 404
    assert client.get("/api/sessions/999/board").status_code == 404
    assert client.post("/api/sessions/999/picks", json={"player_id": "x"}).status_code == 404
    assert client.post("/api/sessions/999/picks/undo").status_code == 404
    assert client.post("/api/sessions", json={"league_id": 999}).status_code == 404


def test_a_session_whose_league_vanished_is_a_404(tmp_path):
    """Sessions outlive their league only if something has gone wrong; say so
    rather than raising."""
    settings = Settings(data_dir=tmp_path / "data")
    app = create_app(settings)
    conn = app.state.db
    league_id = repo.create_league(
        conn,
        LeagueConfig(scoring=ScoringSettings.preset("ppr")),
        scoring_preset="ppr",
        user_id="local",
    )
    session_id = repo.create_session(conn, league_id, "orphan", user_id="local")
    with conn:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("DELETE FROM league WHERE id = ?", (league_id,))
    assert TestClient(app).get(f"/api/sessions/{session_id}").status_code == 404


def test_session_listing(client):
    league = client.post("/api/leagues", json={"num_teams": 12}).json()
    client.post("/api/sessions", json={"league_id": league["id"], "name": "one"})
    client.post("/api/sessions", json={"league_id": league["id"], "name": "two"})
    names = [s["name"] for s in client.get("/api/sessions").json()]
    assert names == ["two", "one"]  # newest first


# --- degraded data sources --------------------------------------------------


def only(*working, fixture_fetcher):
    """A fetcher that serves the named sources and fails everything else."""

    def fetch(spec: RequestSpec) -> RawPayload:
        if any(fragment in spec.url for fragment in working):
            return fixture_fetcher(spec)
        raise ConnectionError(f"source down: {spec.url}")

    return fetch


SPINE = ("players/nfl", "projections/nfl")


@pytest.mark.parametrize(
    ("working", "lost"),
    [
        (SPINE, "everything optional"),
        ((*SPINE, "db_playerids"), "adp and tiers"),
        ((*SPINE, "fantasyfootballcalculator"), "tiers and crosswalk"),
        ((*SPINE, "fftiers"), "adp and crosswalk"),
    ],
)
def test_pool_survives_any_optional_source_failing(tmp_path, fixture_fetcher, working, lost):
    """Losing an optional source costs its columns, never the pool."""
    store = SnapshotStore(tmp_path / lost, only(*working, fixture_fetcher=fixture_fetcher))
    result = build_pool(
        store,
        LeagueConfig(scoring=ScoringSettings.preset("half_ppr")),
        season=2026,
        scoring_preset="half_ppr",
    )
    assert len(result.players) >= 15
    assert all(p.points > 0 for p in result.players)


def test_pool_drops_players_below_the_points_floor(tmp_path, fixture_fetcher):
    store = SnapshotStore(tmp_path, fixture_fetcher)
    league = LeagueConfig(scoring=ScoringSettings.preset("half_ppr"))
    everyone = build_pool(store, league, season=2026, min_points=0.0)
    stars = build_pool(store, league, season=2026, min_points=250.0)
    assert len(stars.players) < len(everyone.players)
    assert all(p.points >= 250 for p in stars.players)


def test_pool_ignores_projections_for_unknown_players(tmp_path, fixture_fetcher):
    """A projection row whose player is missing from the universe is skipped,
    not crashed on."""

    def extra_ghost(spec):
        raw = fixture_fetcher(spec)
        if "projections/nfl" in spec.url:
            rows = json.loads(raw.body)
            rows.append({"player_id": "ghost", "stats": {"rec": 90.0, "rec_yd": 1200.0}})
            return RawPayload(body=json.dumps(rows).encode(), content_type=raw.content_type)
        return raw

    store = SnapshotStore(tmp_path, extra_ghost)
    result = build_pool(store, LeagueConfig(scoring=ScoringSettings.preset("ppr")), season=2026)
    assert "ghost" not in {p.player_id for p in result.players}


# --- engine edges -----------------------------------------------------------


def test_blend_adp_rejects_nonpositive_weights():
    assert blend_adp({"sleeper": 10.0}, {"sleeper": 0.0}) is None


def test_no_need_bonus_for_a_position_the_league_never_starts():
    league = LeagueConfig(
        scoring=ScoringSettings.preset("ppr"), roster=RosterSlots(k=0, dst=0, flex=0)
    )
    out = recommend(
        [Candidate(player_id="k", name="Kicker", position="K", points=120, vorp=5)],
        league=league,
        my_counts={},
        current_pick=1,
        current_round=15,
        total_rounds=15,
    )
    assert not any("still need" in r for r in out[0].reasons)


# --- the SSE stream ---------------------------------------------------------


def fake_request(app) -> Request:
    """The events endpoint only reaches for app.state, so a stand-in keeps these
    tests on our streaming logic rather than on ASGI transport buffering."""
    return cast(Request, SimpleNamespace(app=app))


async def open_stream(app, session_id) -> AsyncGenerator[str, None]:
    resp = await session_events(fake_request(app), session_id, SessionUser("local", ""))
    assert resp.media_type == "text/event-stream"
    return cast(AsyncGenerator[str, None], resp.body_iterator)


def start_session(tmp_path, name):
    app = create_app(Settings(data_dir=tmp_path / "data"))
    league_id = repo.create_league(
        app.state.db,
        LeagueConfig(scoring=ScoringSettings.preset("ppr")),
        scoring_preset="ppr",
        user_id="local",
    )
    return app, repo.create_session(app.state.db, league_id, name, user_id="local")


async def next_chunk(chunks):
    return await asyncio.wait_for(anext(chunks), timeout=2)


def test_sse_stream_delivers_published_events(tmp_path):
    app, session_id = start_session(tmp_path, "sse")

    async def scenario():
        chunks = await open_stream(app, session_id)
        assert await next_chunk(chunks) == "event: connected\ndata: {}\n\n"

        app.state.events.publish(session_id, "pick_recorded", {"player_id": "x"})
        payload = await next_chunk(chunks)
        assert payload.startswith("event: pick_recorded")
        assert json.loads(payload.split("data: ", 1)[1]) == {"player_id": "x"}

        await chunks.aclose()
        assert app.state.events.subscriber_count(session_id) == 0

    asyncio.run(asyncio.wait_for(scenario(), timeout=10))


def test_publish_from_a_worker_thread_wakes_the_stream(tmp_path):
    """Picks are recorded by synchronous endpoints running in FastAPI's
    threadpool, so delivery has to cross threads. put_nowait alone would enqueue
    the item without ever waking the waiting stream."""
    app, session_id = start_session(tmp_path, "threaded")

    async def scenario():
        chunks = await open_stream(app, session_id)
        await next_chunk(chunks)  # connected

        await asyncio.to_thread(
            app.state.events.publish, session_id, "pick_recorded", {"from": "worker"}
        )
        assert '"from": "worker"' in await next_chunk(chunks)
        await chunks.aclose()

    asyncio.run(asyncio.wait_for(scenario(), timeout=10))


def test_sse_emits_keepalives_while_a_draft_is_quiet(tmp_path, monkeypatch):
    """Proxies drop idle connections, and a draft sits quiet while somebody
    deliberates."""
    from draftkit.api import sessions as sessions_api

    monkeypatch.setattr(sessions_api, "KEEPALIVE_SECONDS", 0.05)
    app, session_id = start_session(tmp_path, "quiet")

    async def scenario():
        chunks = await open_stream(app, session_id)
        await next_chunk(chunks)  # connected
        # Two in a row: the stream has to keep looping, not emit one and stop.
        assert await next_chunk(chunks) == ": keepalive\n\n"
        assert await next_chunk(chunks) == ": keepalive\n\n"
        # ...and a pick published after the quiet stretch still arrives.
        app.state.events.publish(session_id, "pick_recorded", {"late": True})
        assert '"late": true' in await next_chunk(chunks)
        assert app.state.events.subscriber_count(session_id) == 1
        await chunks.aclose()
        assert app.state.events.subscriber_count(session_id) == 0

    asyncio.run(asyncio.wait_for(scenario(), timeout=10))


def test_events_endpoint_rejects_an_unknown_session(client):
    assert client.get("/api/sessions/999/events").status_code == 404


# --- production wiring ------------------------------------------------------


def build_static(tmp_path):
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html><title>draftkit</title>")
    (static / "assets" / "app.js").write_text("console.log(1)")
    (static / "favicon.svg").write_text("<svg/>")
    return static


def test_spa_serves_deep_links_and_real_files(tmp_path):
    static = build_static(tmp_path)
    client = TestClient(
        create_app(Settings(data_dir=tmp_path / "data", static_dir=static)),
        raise_server_exceptions=False,
    )
    assert "draftkit" in client.get("/").text
    assert "draftkit" in client.get("/draft/7").text  # deep link gets the shell
    assert client.get("/favicon.svg").text == "<svg/>"  # real files still win
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/api/health").json()["status"] == "ok"  # API is not shadowed


def test_spa_without_a_build_says_so(tmp_path):
    static = build_static(tmp_path)
    (static / "index.html").unlink()
    client = TestClient(
        create_app(Settings(data_dir=tmp_path / "data", static_dir=static)),
        raise_server_exceptions=False,
    )
    assert client.get("/draft/7").status_code == 404


def test_cors_headers_when_configured(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", cors_origins=["http://localhost:5173"])
    client = TestClient(create_app(settings))
    resp = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"


# --- the one function that talks to the network -----------------------------


def test_http_fetch_returns_body_and_content_type(monkeypatch):
    def fake_get(url, headers=None, timeout=None, follow_redirects=None):
        return httpx.Response(
            200,
            content=b"hello",
            headers={"content-type": "text/csv"},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    raw = http_fetch(RequestSpec(url="https://example.test/x"))
    assert raw.body == b"hello"
    assert raw.content_type == "text/csv"


def test_http_fetch_raises_on_error_status(monkeypatch):
    def fake_get(url, headers=None, timeout=None, follow_redirects=None):
        return httpx.Response(503, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    with pytest.raises(httpx.HTTPStatusError):
        http_fetch(RequestSpec(url="https://example.test/x"))


# --- migrations -------------------------------------------------------------


def test_migrations_are_idempotent(tmp_path):
    """Every migration runs once on a fresh database and never again. Asserted
    as a property, not a hardcoded list, so adding one cannot break this."""
    from draftkit.db.connection import MIGRATIONS_DIR

    on_disk = sorted(p.name for p in MIGRATIONS_DIR.glob("*.sql"))
    conn = connect(tmp_path / "app.db")
    assert migrate(conn) == on_disk
    assert migrate(conn) == []


# --- degenerate shapes ------------------------------------------------------


def test_baselines_handle_a_roster_with_no_eligible_starters():
    """A flex with nothing flex-eligible, and a bench with nothing to stash:
    nonsensical, but it must not divide by zero."""
    from draftkit.engine.baselines import drafted_by_position, starters_by_position
    from draftkit.models.league import RosterSlots

    empty_flex = starters_by_position(RosterSlots(qb=1, rb=0, wr=0, te=0, flex=2, k=1, dst=1))
    assert empty_flex["RB"] == 0
    assert empty_flex["QB"] == 1  # the flex simply goes nowhere

    no_depth = drafted_by_position(RosterSlots(qb=0, rb=0, wr=0, te=0, flex=0, k=1, dst=1, bench=5))
    assert no_depth["K"] == 1


def test_resolver_skips_crosswalk_rows_with_no_name_and_teamless_players():
    from draftkit.identity.resolver import Resolver

    players = [{"sleeper_id": "1", "name": "Free Agent", "position": "WR", "team": None}]
    crosswalk = [
        {"sleeper_id": "2", "name": "", "merge_name": "", "position": "RB", "team": "SF"},
        {"sleeper_id": "3", "name": "Real Person", "merge_name": "real person", "position": "TE"},
    ]
    r = Resolver.build(players, crosswalk)
    assert r.resolve("Free Agent", "WR").sleeper_id == "1"  # indexed without a team
    assert r.resolve("Real Person", "TE").sleeper_id == "3"


def test_players_with_no_adp_for_this_format_still_make_the_pool(tmp_path, fixture_fetcher):
    """A rookie or a late addition may carry projections but no ADP yet."""

    def strip_one_adp(spec):
        raw = fixture_fetcher(spec)
        if "projections/nfl" in spec.url:
            rows = json.loads(raw.body)
            for key in list(rows[0]["stats"]):
                if key.startswith("adp_"):
                    del rows[0]["stats"][key]
            return RawPayload(body=json.dumps(rows).encode(), content_type=raw.content_type)
        return raw

    store = SnapshotStore(tmp_path, strip_one_adp)
    result = build_pool(
        store,
        LeagueConfig(scoring=ScoringSettings.preset("half_ppr")),
        season=2026,
        scoring_preset="half_ppr",
    )
    # He keeps whatever other sources know about him, and still gets scored.
    stripped = [p for p in result.players if "sleeper" not in p.adp_by_source]
    assert stripped, "expected a player with no Sleeper ADP for this format"
    assert all(p.points > 0 for p in result.players)


def test_health_reports_the_newest_of_several_snapshots(tmp_path, fixture_fetcher):
    """Snapshot ages must reflect the newest file, whatever order they enumerate in."""
    from draftkit.sources import sleeper_players

    store = SnapshotStore(tmp_path, fixture_fetcher)
    store.get(sleeper_players)
    directory = next((tmp_path / "sleeper_players").iterdir())
    original = next(directory.glob("*.snap"))
    for stamp in ("19990101T000000", "29990101T000000"):
        (directory / f"{stamp}.snap").write_bytes(original.read_bytes())
        (directory / f"{stamp}.meta.json").write_text(
            json.dumps(
                {
                    "fetched_at": f"{stamp[:4]}-01-01T00:00:00+00:00",
                    "content_type": "application/json",
                }
            )
        )
    # The far-future snapshot wins, so the reported age is negative, not stale.
    assert store.ages()["sleeper_players"] < 0


def test_board_after_the_final_pick(tmp_path, fixture_fetcher):
    """A finished draft has nobody on the clock and nothing to recommend."""
    app = create_app(Settings(data_dir=tmp_path / "data"))
    app.state.snapshot_store = SnapshotStore(tmp_path / "snapshots", fixture_fetcher)
    client = TestClient(app)
    league = client.post("/api/leagues", json={"num_teams": 4, "my_slot": 1, "rounds": 1}).json()
    sid = client.post("/api/sessions", json={"league_id": league["id"]}).json()["session"]["id"]

    board = client.get(f"/api/sessions/{sid}/board").json()
    for player in board["available"][:4]:
        client.post(f"/api/sessions/{sid}/picks", json={"player_id": player["player_id"]})

    done = client.get(f"/api/sessions/{sid}/board").json()
    assert done["picks_made"] == done["total_picks"] == 4
    assert done["on_the_clock"] is None
    assert done["recommendations"] == []
    assert done["picks_until_my_turn"] is None


def test_market_rows_for_players_we_do_not_know_are_skipped(tmp_path, fixture_fetcher):
    """A market source lists players our universe has never heard of (rookies
    mid-signing, retirements). They are dropped, not crashed on, and they are
    reported so an override can be written."""

    def with_a_stranger(spec):
        raw = fixture_fetcher(spec)
        if "fantasyfootballcalculator" in spec.url:
            payload = json.loads(raw.body)
            payload["players"].append(
                {
                    "player_id": 99999,
                    "name": "Nobody Whatsoever",
                    "position": "WR",
                    "team": "FA",
                    "adp": 200.0,
                    "bye": 7,
                }
            )
            return RawPayload(body=json.dumps(payload).encode(), content_type=raw.content_type)
        return raw

    store = SnapshotStore(tmp_path, with_a_stranger)
    result = build_pool(
        store,
        LeagueConfig(scoring=ScoringSettings.preset("half_ppr")),
        season=2026,
        scoring_preset="half_ppr",
    )
    assert "Nobody Whatsoever" not in {p.name for p in result.players}
    assert any(u["name"] == "Nobody Whatsoever" for u in result.unmatched)
