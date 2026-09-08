import os
from pathlib import Path

import pytest

from draftkit.sources.base import RawPayload, RequestSpec

FIXTURES = Path(__file__).parent / "fixtures"

_URL_TO_FIXTURE = [
    # Order matters throughout: matching is by substring, first hit wins, and
    # the trending URLs contain the bare players URL.
    ("trending/add", FIXTURES / "sleeper" / "trending_add.json", "application/json"),
    ("trending/drop", FIXTURES / "sleeper" / "trending_drop.json", "application/json"),
    ("players/nfl", FIXTURES / "sleeper" / "players.json", "application/json"),
    ("projections/nfl", FIXTURES / "sleeper" / "projections.json", "application/json"),
    ("fantasyfootballcalculator", FIXTURES / "ffcalc" / "adp_half_ppr_12.json", "application/json"),
    ("fftiers", FIXTURES / "borischen" / "weekly-ALL-HALF-PPR.csv", "text/csv"),
    ("db_playerids", FIXTURES / "dp" / "db_playerids.csv", "text/plain"),
    ("cbssports", FIXTURES / "cbs" / "rankings.json", "application/json"),
    (
        "fantasypros",
        FIXTURES / "fantasypros" / "half_ppr_cheatsheet.html",
        "text/html; charset=UTF-8",
    ),
    ("pub-api-ro", FIXTURES / "yahoo" / "draft_analysis.json", "application/json"),
    ("myfantasyleague", FIXTURES / "mfl" / "adp.json", "application/json"),
    ("/leagues/", FIXTURES / "espn" / "league_settings.json", "application/json"),
    ("leaguedefaults", FIXTURES / "espn" / "projections.json", "application/json"),
    ("lm-api-reads", FIXTURES / "espn" / "players.json", "application/json"),
]


def load_fixture(url_fragment: str) -> RawPayload:
    for fragment, path, content_type in _URL_TO_FIXTURE:
        if fragment == url_fragment:
            return RawPayload(body=path.read_bytes(), content_type=content_type)
    raise KeyError(url_fragment)


@pytest.fixture(autouse=True, scope="session")
def settings_ignore_developer_env():
    """Tests must never read the developer's own .env.

    Settings() loads .env and the DRAFTKIT_ prefix on every construction, so
    the machine running the suite could change its result. It did: a local
    DRAFTKIT_STATIC_DIR meant no test ever built an app WITHOUT a frontend
    mount, which is the default every user runs — the branch went uncovered
    here and covered in CI, so the 100% gate passed or failed depending on
    whose laptop it was. The same leak would happily hand a test real ESPN
    cookies or a real redirect URI.
    """
    from draftkit.config import Settings

    original_env_file = Settings.model_config.get("env_file")
    Settings.model_config["env_file"] = None
    saved = {k: v for k, v in os.environ.items() if k.startswith("DRAFTKIT_")}
    for key in saved:
        del os.environ[key]
    yield
    os.environ.update(saved)
    Settings.model_config["env_file"] = original_env_file


@pytest.fixture(autouse=True)
def isolated_pool_cache():
    """Every test starts with a cold pool cache. Without this, a test that
    builds a pool could serve it to a later test with the same league config
    — notably masking what the offline-fallback test actually verifies."""
    from draftkit.pool import clear_pool_cache

    clear_pool_cache()
    yield
    clear_pool_cache()


@pytest.fixture
def fixture_fetcher():
    """A Fetcher serving recorded fixture payloads by URL match."""

    def fetch(spec: RequestSpec) -> RawPayload:
        for fragment, path, content_type in _URL_TO_FIXTURE:
            if fragment in spec.url:
                return RawPayload(body=path.read_bytes(), content_type=content_type)
        raise AssertionError(f"no fixture for {spec.url}")

    return fetch


@pytest.fixture
def failing_fetcher():
    def fetch(spec: RequestSpec) -> RawPayload:
        raise ConnectionError("network down")

    return fetch
