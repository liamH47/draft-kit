"""How the multi-source pool joins: blended points, extra ADP markets and
ranking lists, and the bye-week fallback chain.

Each of these sources is optional by construction — the pool must build with
any subset of them, because on draft night an unreachable feed costs its
columns and nothing else.
"""

import json
from contextlib import suppress
from pathlib import Path

import pytest

from draftkit.models.league import LeagueConfig, ScoringSettings
from draftkit.pool import build_pool
from draftkit.snapshots.store import SnapshotStore
from draftkit.sources.base import RawPayload
from tests.conftest import _URL_TO_FIXTURE


def league() -> LeagueConfig:
    return LeagueConfig(scoring=ScoringSettings.preset("half_ppr"))


def fetcher_without(*fragments: str):
    """Serve the recorded fixtures, but fail for the named sources."""

    def fetch(spec):
        for fragment, path, content_type in _URL_TO_FIXTURE:
            if fragment in spec.url:
                if fragment in fragments:
                    raise ConnectionError(f"{fragment} is down")
                return RawPayload(body=path.read_bytes(), content_type=content_type)
        raise AssertionError(f"no fixture for {spec.url}")

    return fetch


def build(tmp_path, fetch) -> dict:
    store = SnapshotStore(tmp_path / "snaps", fetch)
    result = build_pool(store, league(), season=2026, scoring_preset="half_ppr")
    return {p.name: p for p in result.players}


def test_points_blend_the_projection_sources(tmp_path, fixture_fetcher):
    by_name = build(tmp_path, fixture_fetcher)
    cmc = by_name["Christian McCaffrey"]
    assert cmc.extra["points.sleeper"] != cmc.extra["points.espn"]
    assert cmc.points == pytest.approx(
        (cmc.extra["points.sleeper"] + cmc.extra["points.espn"]) / 2, abs=0.01
    )


def test_a_player_only_one_source_projects_keeps_that_projection(tmp_path):
    """ESPN covers a few hundred players; Sleeper covers thousands. A player
    outside ESPN's list must not be blended toward zero."""
    solo = build(tmp_path, fetcher_without("leaguedefaults"))
    both = build(tmp_path / "b", None or fetcher_without())
    name = "Christian McCaffrey"
    assert "points.espn" not in solo[name].extra
    assert solo[name].points != both[name].points


def test_yahoo_and_cbs_add_a_market_and_a_list(tmp_path, fixture_fetcher):
    by_name = build(tmp_path, fixture_fetcher)
    gibbs = by_name["Jahmyr Gibbs"]
    assert "yahoo" in gibbs.adp_by_source
    assert "cbs" in gibbs.rank_by_source
    assert gibbs.extra["yahoo.average_cost"] > 0
    assert gibbs.consensus_rank is not None


def test_the_pool_still_builds_when_every_optional_source_is_down(tmp_path):
    """The spine is Sleeper players + projections; everything else is optional."""
    by_name = build(
        tmp_path,
        fetcher_without(
            "leaguedefaults",
            "cbssports",
            "pub-api-ro",
            "fantasyfootballcalculator",
            "fftiers",
            "lm-api-reads",
            "db_playerids",
        ),
    )
    assert len(by_name) >= 15
    cmc = by_name["Christian McCaffrey"]
    assert cmc.points > 0
    assert cmc.adp_by_source == {"sleeper": pytest.approx(cmc.adp_by_source.get("sleeper", 0))}


def test_bye_falls_back_past_a_source_that_lacks_the_player(tmp_path, fixture_fetcher):
    """FFC lists ~250 players; Yahoo and CBS fill byes it never carries."""
    assert build(tmp_path, fixture_fetcher)["Jahmyr Gibbs"].bye is not None
    without_ffc = build(tmp_path / "b", fetcher_without("fantasyfootballcalculator"))
    assert without_ffc["Jahmyr Gibbs"].bye is not None  # Yahoo/CBS carried it


def test_the_yahoo_walk_stops_at_a_page_with_no_adp(tmp_path):
    """Yahoo pages 25 at a time and the tail has no ADP at all. Walking to the
    hard cap would cost 16 requests where 1 will do."""
    calls = []
    page = json.loads(
        (Path(__file__).parent / "fixtures" / "yahoo" / "draft_analysis.json").read_text()
    )
    players = page["fantasy_content"]["game"][1]["players"]
    for key, wrapped in players.items():
        if key == "count":
            continue
        for fragment in wrapped["player"][1:]:
            if isinstance(fragment, dict) and "draft_analysis" in fragment:
                for item in fragment["draft_analysis"]:
                    if isinstance(item, dict) and "average_pick" in item:
                        item["average_pick"] = "-"
    empty = json.dumps(page).encode()

    def fetch(spec):
        for fragment, path, content_type in _URL_TO_FIXTURE:
            if fragment in spec.url:
                if fragment == "pub-api-ro":
                    calls.append(spec.url)
                    return RawPayload(body=empty, content_type=content_type)
                return RawPayload(body=path.read_bytes(), content_type=content_type)
        raise AssertionError(f"no fixture for {spec.url}")

    build(tmp_path, fetch)
    assert len(calls) == 1


def test_rows_we_cannot_resolve_are_skipped_not_crashed_on(tmp_path):
    """CBS and the projection feeds list players our universe never heard of
    (camp bodies, practice-squad call-ups). They are dropped quietly."""

    def fetch(spec):
        for fragment, path, content_type in _URL_TO_FIXTURE:
            if fragment not in spec.url:
                continue
            body = path.read_bytes()
            if fragment == "cbssports":
                payload = json.loads(body)
                payload["body"]["rankings"]["players"].append(
                    {"id": "999999", "fullname": "Nobody Atall", "rank": "300", "position": "WR"}
                )
                body = json.dumps(payload).encode()
            if fragment == "leaguedefaults":
                payload = json.loads(body)
                # A projection that scores zero must not replace real points.
                payload["players"].append(
                    {
                        "id": 888888,
                        "player": {
                            "id": 888888,
                            "fullName": "Christian McCaffrey",
                            "defaultPositionId": 2,
                            "stats": [
                                {
                                    "statSourceId": 1,
                                    "statSplitTypeId": 0,
                                    "seasonId": 2099,
                                    "stats": {},
                                    "appliedTotal": 0,
                                }
                            ],
                        },
                    }
                )
                body = json.dumps(payload).encode()
            return RawPayload(body=body, content_type=content_type)
        raise AssertionError(f"no fixture for {spec.url}")

    by_name = build(tmp_path, fetch)
    assert "Nobody Atall" not in by_name
    assert by_name["Christian McCaffrey"].points > 0


def test_market_movement_is_reported_once_there_is_history(tmp_path, fixture_fetcher):
    """An injury ahead of somebody shows up as his ADP falling. It needs two
    readings of the SAME market to mean anything, so it is absent until then."""
    import json as _json
    from datetime import UTC, datetime, timedelta

    store = SnapshotStore(tmp_path / "snaps", fixture_fetcher)
    league_cfg = league()
    first = {p.name: p for p in build_pool(store, league_cfg, season=2026).players}
    assert first["Christian McCaffrey"].adp_shift is None  # one reading is not a trend

    # Backdate a second FFC snapshot in which he was going three picks later.
    directory = next((tmp_path / "snaps" / "ffcalc").iterdir())
    payload = _json.loads(next(directory.glob("*.snap")).read_bytes())
    for row in payload["players"]:
        if row["name"] == "Christian McCaffrey":
            row["adp"] = row["adp"] + 3.0
    stamp = "20260101T000000"
    (directory / f"{stamp}.snap").write_bytes(_json.dumps(payload).encode())
    (directory / f"{stamp}.meta.json").write_text(
        _json.dumps(
            {
                "fetched_at": (datetime.now(UTC) - timedelta(hours=8)).isoformat(),
                "content_type": "application/json",
            }
        )
    )

    moved = {p.name: p for p in build_pool(store, league_cfg, season=2026).players}
    cmc = moved["Christian McCaffrey"]
    assert cmc.adp_shift == pytest.approx(-3.0)
    assert cmc.adp_shift_sources == 1  # real, but uncorroborated
    # Everyone else held still.
    assert moved["Jahmyr Gibbs"].adp_shift == pytest.approx(0.0)


def test_a_broken_history_read_costs_movement_and_nothing_else(tmp_path, fixture_fetcher):
    """Movement is a nicety; the board is not. If the history read throws,
    the pool must still build."""
    store = SnapshotStore(tmp_path / "snaps", fixture_fetcher)

    def explode(*args, **kwargs):
        raise RuntimeError("history is unreadable")

    store.earliest_within = explode  # type: ignore[method-assign]
    by_name = {p.name: p for p in build_pool(store, league(), season=2026).players}
    assert len(by_name) >= 15
    assert by_name["Christian McCaffrey"].adp_shift is None


def test_a_previous_snapshot_row_we_cannot_resolve_is_ignored(tmp_path, fixture_fetcher):
    """Yesterday's file can name players today's does not, and vice versa."""
    import json as _json
    from datetime import UTC, datetime, timedelta

    store = SnapshotStore(tmp_path / "snaps", fixture_fetcher)
    build_pool(store, league(), season=2026)
    directory = next((tmp_path / "snaps" / "ffcalc").iterdir())
    payload = _json.loads(next(directory.glob("*.snap")).read_bytes())
    payload["players"].append(
        {"name": "Departed Camp Body", "position": "WR", "team": "SF", "adp": 190.0}
    )
    for row in payload["players"]:
        row.pop("adp", None) if row["name"] == "Jahmyr Gibbs" else None
    stamp = "20260101T000000"
    (directory / f"{stamp}.snap").write_bytes(_json.dumps(payload).encode())
    (directory / f"{stamp}.meta.json").write_text(
        _json.dumps(
            {
                "fetched_at": (datetime.now(UTC) - timedelta(hours=8)).isoformat(),
                "content_type": "application/json",
            }
        )
    )
    by_name = {p.name: p for p in build_pool(store, league(), season=2026).players}
    # A player with no ADP in the old file has nothing to compare against.
    assert by_name["Jahmyr Gibbs"].adp_shift is None
    assert by_name["Christian McCaffrey"].adp_shift == pytest.approx(0.0)


def test_a_market_bucket_never_becomes_a_draft_price(tmp_path, fixture_fetcher):
    """A source that dumps its undrafted players at one trailing number must
    not make them look like players falling to it."""
    import json as _json

    def fetch(spec):
        for fragment, path, content_type in _URL_TO_FIXTURE:
            if fragment not in spec.url:
                continue
            body = path.read_bytes()
            if fragment == "lm-api-reads":
                payload = _json.loads(body)
                # Everybody ESPN does not price lands in one jittered band.
                for i, entry in enumerate(payload):
                    player = entry.get("player") or entry
                    player.setdefault("ownership", {})["averageDraftPosition"] = (
                        170.0 + (i % 4) * 0.01
                    )
                # ...and there are always far more of them than of real prices.
                for i in range(40):
                    payload.append(
                        {
                            "id": 900000 + i,
                            "player": {
                                "id": 900000 + i,
                                "fullName": f"Undrafted Body {i}",
                                "defaultPositionId": 3,
                                "ownership": {"averageDraftPosition": 170.0 + (i % 4) * 0.01},
                            },
                        }
                    )
                body = _json.dumps(payload).encode()
            return RawPayload(body=body, content_type=content_type)
        raise AssertionError(f"no fixture for {spec.url}")

    by_name = build(tmp_path, fetch)
    assert all("espn" not in p.adp_by_source for p in by_name.values())
    # The other markets still price the board.
    assert by_name["Christian McCaffrey"].adp is not None


def test_a_player_no_market_prices_has_no_edge_over_the_market(tmp_path, fixture_fetcher):
    """You cannot be a sleeper relative to a market that never listed you."""
    import json as _json

    def fetch(spec):
        for fragment, path, content_type in _URL_TO_FIXTURE:
            if fragment not in spec.url:
                continue
            body = path.read_bytes()
            if fragment == "projections/nfl":
                payload = _json.loads(body)
                for row in payload:
                    if row.get("player_id") == "4034":  # McCaffrey: unpriced everywhere
                        row["stats"] = {
                            k: v for k, v in row["stats"].items() if not k.startswith("adp_")
                        }
                body = _json.dumps(payload).encode()
            if fragment in ("fantasyfootballcalculator", "lm-api-reads", "pub-api-ro"):
                raise ConnectionError("no market today")
            return RawPayload(body=body, content_type=content_type)
        raise AssertionError(f"no fixture for {spec.url}")

    by_name = build(tmp_path, fetch)
    cmc = by_name["Christian McCaffrey"]
    assert cmc.adp is None
    assert cmc.market_edge is None
    assert cmc.rank >= 1  # still ranked on his own merits


def _backdate(tmp_path, source_dir, mutate, hours=8):
    """Write an older snapshot of a source, with its prices altered, so the
    pool has something to compare today's reading against."""
    import json as _json
    from datetime import UTC, datetime, timedelta

    stamp = "20260101T000000"
    meta = _json.dumps(
        {
            "fetched_at": (datetime.now(UTC) - timedelta(hours=hours)).isoformat(),
            "content_type": "application/json",
        }
    )
    # Every parameter set the source was fetched with: a real warm writes them
    # all, and Yahoo in particular pages its board across sixteen of them.
    for directory in (tmp_path / "snaps" / source_dir).iterdir():
        payload = _json.loads(next(directory.glob("*.snap")).read_bytes())
        mutate(payload)
        (directory / f"{stamp}.snap").write_bytes(_json.dumps(payload).encode())
        (directory / f"{stamp}.meta.json").write_text(meta)


def test_movement_is_averaged_over_the_markets_that_agree(tmp_path, fixture_fetcher):
    """One market moving is noise; several moving together is news, so the
    count of markets that saw both readings travels with the number."""
    store = SnapshotStore(tmp_path / "snaps", fixture_fetcher)
    build_pool(store, league(), season=2026)

    def older_ffc(payload):
        for row in payload["players"]:
            if row["name"] == "Christian McCaffrey":
                row["adp"] += 4.0

    def older_espn(payload):
        for entry in payload:
            player = entry.get("player") or entry
            if player.get("fullName") == "Christian McCaffrey":
                player["ownership"]["averageDraftPosition"] += 2.0

    _backdate(tmp_path, "ffcalc", older_ffc)
    _backdate(tmp_path, "espn_market", older_espn)

    cmc = {p.name: p for p in build_pool(store, league(), season=2026).players}[
        "Christian McCaffrey"
    ]
    assert cmc.adp_shift_sources == 2
    assert cmc.adp_shift == pytest.approx(-3.0)  # the mean of -4 and -2


def test_yahoo_history_walks_its_pages_like_its_prices(tmp_path, fixture_fetcher):
    """Yahoo prices 25 players a page, so its past is paged too."""
    store = SnapshotStore(tmp_path / "snaps", fixture_fetcher)
    build_pool(store, league(), season=2026)

    def older_yahoo(payload):
        for wrapped in payload["fantasy_content"]["game"][1]["players"].values():
            if not isinstance(wrapped, dict):
                continue
            for fragment in wrapped["player"][1:]:
                if not (isinstance(fragment, dict) and "draft_analysis" in fragment):
                    continue
                for item in fragment["draft_analysis"]:
                    if not (isinstance(item, dict) and "average_pick" in item):
                        continue
                    with suppress(ValueError):  # Yahoo writes "-" for no data
                        item["average_pick"] = str(float(item["average_pick"]) + 5.0)

    _backdate(tmp_path, "yahoo_adp", older_yahoo)

    gibbs = {p.name: p for p in build_pool(store, league(), season=2026).players}["Jahmyr Gibbs"]
    assert gibbs.adp_shift is not None and gibbs.adp_shift < 0  # taken earlier now
    assert gibbs.adp_shift_sources == 1  # only Yahoo has a second reading
