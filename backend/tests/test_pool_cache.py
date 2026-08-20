"""The pool cache: a board read after every pick must not cost an ~800ms
rebuild, but a cached pool must never outlive the snapshots or config it was
built from."""

import draftkit.pool as pool_mod
from draftkit.models.league import LeagueConfig, RosterSlots, ScoringSettings
from draftkit.pool import build_pool_cached
from draftkit.snapshots.store import SnapshotStore
from draftkit.sources import sleeper_players


def league(**kwargs) -> LeagueConfig:
    return LeagueConfig(scoring=ScoringSettings.preset("half_ppr"), **kwargs)


def store_for(tmp_path, fixture_fetcher) -> SnapshotStore:
    return SnapshotStore(tmp_path / "snapshots", fixture_fetcher)


def test_repeat_reads_reuse_the_built_pool(tmp_path, fixture_fetcher):
    store = store_for(tmp_path, fixture_fetcher)
    first = build_pool_cached(store, league(), season=2026)
    second = build_pool_cached(store, league(), season=2026)
    assert second is first


def test_a_new_snapshot_invalidates(tmp_path, fixture_fetcher):
    store = store_for(tmp_path, fixture_fetcher)
    first = build_pool_cached(store, league(), season=2026)
    # A warm (force=True) writes a new snapshot file; the token must change.
    store.get(sleeper_players, force=True)
    second = build_pool_cached(store, league(), season=2026)
    assert second is not first
    assert len(second.players) == len(first.players)


def test_a_different_league_config_is_a_different_pool(tmp_path, fixture_fetcher):
    store = store_for(tmp_path, fixture_fetcher)
    twelve = build_pool_cached(store, league(), season=2026)
    eight = build_pool_cached(
        store, league(num_teams=8, roster=RosterSlots(wr=3)), season=2026
    )
    assert eight is not twelve


def test_the_cache_expires_so_source_ttls_still_apply(tmp_path, fixture_fetcher, monkeypatch):
    """A permanent cache would skip store.get() forever and a lapsed source
    would never refetch. Past the cap, the pool rebuilds (store.get still
    decides disk vs network exactly as before)."""
    store = store_for(tmp_path, fixture_fetcher)
    first = build_pool_cached(store, league(), season=2026)

    real_monotonic = pool_mod.time.monotonic
    monkeypatch.setattr(
        pool_mod.time,
        "monotonic",
        lambda: real_monotonic() + pool_mod._POOL_CACHE_SECONDS + 1,
    )
    second = build_pool_cached(store, league(), season=2026)
    assert second is not first


def test_freshness_token_is_empty_without_snapshots(tmp_path):
    assert SnapshotStore(tmp_path / "nothing-here").freshness_token() == ()
