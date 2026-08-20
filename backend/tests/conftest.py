from pathlib import Path

import pytest

from draftkit.sources.base import RawPayload, RequestSpec

FIXTURES = Path(__file__).parent / "fixtures"

_URL_TO_FIXTURE = [
    ("players/nfl", FIXTURES / "sleeper" / "players.json", "application/json"),
    ("projections/nfl", FIXTURES / "sleeper" / "projections.json", "application/json"),
    ("fantasyfootballcalculator", FIXTURES / "ffcalc" / "adp_half_ppr_12.json", "application/json"),
    ("fftiers", FIXTURES / "borischen" / "weekly-ALL-HALF-PPR.csv", "text/csv"),
    ("db_playerids", FIXTURES / "dp" / "db_playerids.csv", "text/plain"),
    # Order matters: the league URL is more specific than the players URL.
    ("/leagues/", FIXTURES / "espn" / "league_settings.json", "application/json"),
    ("lm-api-reads", FIXTURES / "espn" / "players.json", "application/json"),
]


def load_fixture(url_fragment: str) -> RawPayload:
    for fragment, path, content_type in _URL_TO_FIXTURE:
        if fragment == url_fragment:
            return RawPayload(body=path.read_bytes(), content_type=content_type)
    raise KeyError(url_fragment)


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
