from fastapi.testclient import TestClient

from draftkit.config import Settings
from draftkit.main import create_app
from draftkit.snapshots.store import SnapshotStore


def make_client(tmp_path, fetcher) -> TestClient:
    app = create_app(Settings(data_dir=tmp_path / "data"))
    app.state.snapshot_store = SnapshotStore(tmp_path / "data" / "snapshots", fetcher)
    return TestClient(app)


def test_pool_end_to_end(tmp_path, fixture_fetcher):
    client = make_client(tmp_path, fixture_fetcher)
    resp = client.get("/api/players?scoring=half_ppr&teams=12")
    assert resp.status_code == 200
    body = resp.json()
    players = body["players"]
    assert len(players) >= 15

    by_name = {p["name"]: p for p in players}
    cmc = by_name["Christian McCaffrey"]
    assert cmc["adp"] is not None
    assert set(cmc["adp_by_source"]) == {"sleeper", "ffcalc", "espn"}
    assert cmc["bye"] is not None  # joined from FFC despite name-only match
    assert cmc["tier"] is not None
    assert cmc["tier_expert"] is not None  # Boris Chen join
    assert cmc["rank"] >= 1 and cmc["pos_rank"] >= 1

    walker = by_name["Kenneth Walker III"]  # suffix-normalized join vs FFC
    assert walker["bye"] is not None

    assert body["sources"]["sleeper_players"]["stale"] is False
    assert body["unmatched_count"] >= 1  # "San Francisco Defense" has no clean match


def test_scoring_preset_changes_points(tmp_path, fixture_fetcher):
    client = make_client(tmp_path, fixture_fetcher)
    half = client.get("/api/players?scoring=half_ppr").json()["players"]
    ppr = client.get("/api/players?scoring=ppr").json()["players"]
    half_cmc = next(p for p in half if p["name"] == "Christian McCaffrey")
    ppr_cmc = next(p for p in ppr if p["name"] == "Christian McCaffrey")
    # Points blend every projection source covering a player, so the PPR gain
    # is half a point per source-averaged catch. Assert the property (pass
    # catchers gain, at half a point per catch) rather than one source's
    # reception count.
    gain = ppr_cmc["points"] - half_cmc["points"]
    assert 40 * 0.5 < gain < 90 * 0.5

    half_qb = next(p for p in half if p["name"] == "Josh Allen")
    ppr_qb = next(p for p in ppr if p["name"] == "Josh Allen")
    assert half_qb["points"] == ppr_qb["points"]


def test_offline_serves_stale_pool(tmp_path, fixture_fetcher, failing_fetcher):
    # Warm snapshots, then restart against a dead network: pool still serves.
    make_client(tmp_path, fixture_fetcher).get("/api/players")
    client = make_client(tmp_path, failing_fetcher)
    resp = client.get("/api/players")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["players"]) >= 15


def test_health_reports_snapshot_ages(tmp_path, fixture_fetcher):
    client = make_client(tmp_path, fixture_fetcher)
    client.get("/api/players")
    ages = client.get("/api/health").json()["snapshots"]
    assert "sleeper_players" in ages and "ffcalc" in ages


def test_defenses_join_to_their_market_data(tmp_path, fixture_fetcher):
    """Defenses have no crosswalk id and a different name in every feed, so
    they used to lose ADP and bye entirely."""
    client = make_client(tmp_path, fixture_fetcher)
    players = client.get("/api/players?scoring=half_ppr").json()["players"]
    defenses = [p for p in players if p["position"] == "DEF"]
    assert defenses, "expected a defense in the pool"
    sf = defenses[0]
    assert sf["adp"] is not None, "defense should carry a blended ADP"
    assert sf["bye"] is not None, "defense bye comes only from FFC"
    assert "ffcalc" in sf["adp_by_source"]
