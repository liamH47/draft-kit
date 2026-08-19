import pytest

from draftkit.snapshots.store import SnapshotError, SnapshotStore
from draftkit.sources import sleeper_players
from tests.conftest import load_fixture


def test_fetch_writes_snapshot_and_serves_cache(tmp_path, fixture_fetcher):
    store = SnapshotStore(tmp_path, fixture_fetcher)
    ds, meta = store.get(sleeper_players)
    assert len(ds.rows) > 10
    assert meta.from_cache is False and meta.stale is False

    calls = []

    def counting(spec):
        calls.append(spec.url)
        return fixture_fetcher(spec)

    cached_store = SnapshotStore(tmp_path, counting)
    ds2, meta2 = cached_store.get(sleeper_players)
    assert calls == []  # fresh snapshot within ttl -> no fetch
    assert meta2.from_cache is True and meta2.stale is False
    assert len(ds2.rows) == len(ds.rows)


def test_failure_falls_back_to_stale_snapshot(tmp_path, fixture_fetcher, failing_fetcher):
    SnapshotStore(tmp_path, fixture_fetcher).get(sleeper_players)
    store = SnapshotStore(tmp_path, failing_fetcher)
    ds, meta = store.get(sleeper_players, force=True)
    assert meta.stale is True
    assert len(ds.rows) > 10


def test_failure_with_no_snapshot_raises(tmp_path, failing_fetcher):
    with pytest.raises(SnapshotError):
        SnapshotStore(tmp_path, failing_fetcher).get(sleeper_players)


def test_invalid_payload_falls_back(tmp_path, fixture_fetcher):
    SnapshotStore(tmp_path, fixture_fetcher).get(sleeper_players)

    def html_fetcher(spec):
        raw = load_fixture("players/nfl")
        return type(raw)(body=b"<html>maintenance</html>", content_type="text/html")

    ds, meta = SnapshotStore(tmp_path, html_fetcher).get(sleeper_players, force=True)
    assert meta.stale is True
    assert len(ds.rows) > 10


def test_ages_reports_hours(tmp_path, fixture_fetcher):
    store = SnapshotStore(tmp_path, fixture_fetcher)
    store.get(sleeper_players)
    ages = store.ages()
    assert set(ages) == {"sleeper_players"}
    assert ages["sleeper_players"] < 1.0
