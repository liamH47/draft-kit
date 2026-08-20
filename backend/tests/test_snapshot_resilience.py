"""The snapshot store must not raise while any usable snapshot exists.

This is the read a live draft depends on: every board refresh goes through it,
and a draft cannot be re-run. Each test here corresponds to a way the store
previously failed hard.
"""

import json

import pytest

from draftkit.snapshots.store import SnapshotError, SnapshotStore
from draftkit.sources import sleeper_players
from draftkit.sources.base import RawPayload


def snap_dir(root):
    return next((root / "sleeper_players").iterdir())


def test_survives_a_missing_meta_file(tmp_path, fixture_fetcher, failing_fetcher):
    """A crash between the two writes used to take down the board and /health."""
    SnapshotStore(tmp_path, fixture_fetcher).get(sleeper_players)
    for meta in snap_dir(tmp_path).glob("*.meta.json"):
        meta.unlink()

    store = SnapshotStore(tmp_path, failing_fetcher)
    with pytest.raises(SnapshotError):  # nothing usable left, but a clean error
        store.get(sleeper_players)
    assert store.ages() == {}  # and health still answers


def test_falls_back_past_a_corrupt_newest_snapshot(tmp_path, fixture_fetcher):
    store = SnapshotStore(tmp_path, fixture_fetcher)
    store.get(sleeper_players)
    good = sorted(snap_dir(tmp_path).glob("*.snap"))[-1]

    # A later snapshot that is truncated garbage.
    later = good.with_name("29991231T235959.snap")
    later.write_bytes(b"{ this is not json")
    later.with_suffix(".meta.json").write_text(
        json.dumps({"fetched_at": "2999-12-31T23:59:59+00:00", "content_type": "application/json"})
    )

    dataset, meta = store.get(sleeper_players)
    assert len(dataset.rows) > 10  # walked back to the good one
    assert meta.from_cache is True


def test_unparseable_payload_never_reaches_disk(tmp_path, fixture_fetcher):
    """A body that passes validate() but breaks parse() used to be written
    first, permanently poisoning the newest slot."""
    SnapshotStore(tmp_path, fixture_fetcher).get(sleeper_players)
    before = sorted(p.name for p in snap_dir(tmp_path).glob("*.snap"))

    def validates_but_wont_parse(spec):
        # Valid JSON object, right content type, but the values are not players.
        return RawPayload(
            body=b'{"a":1,"b":2,"c":3,"d":4,"e":5,"f":6,"g":7,"h":8,"i":9,"j":10,"k":11}',
            content_type="application/json",
        )

    store = SnapshotStore(tmp_path, validates_but_wont_parse)
    dataset, meta = store.get(sleeper_players, force=True)
    assert meta.stale is True  # fell back
    assert len(dataset.rows) > 10
    assert sorted(p.name for p in snap_dir(tmp_path).glob("*.snap")) == before


def test_no_partial_snapshot_is_left_discoverable(tmp_path, fixture_fetcher):
    SnapshotStore(tmp_path, fixture_fetcher).get(sleeper_players)
    assert list(snap_dir(tmp_path).glob("*.part")) == []


def test_offline_mode_never_touches_the_network(tmp_path, fixture_fetcher):
    """During a draft a lapsed TTL must not become a blocking fetch."""
    SnapshotStore(tmp_path, fixture_fetcher).get(sleeper_players)

    calls = []

    def counting(spec):
        calls.append(spec.url)
        return fixture_fetcher(spec)

    store = SnapshotStore(tmp_path, counting, offline=True)
    dataset, meta = store.get(sleeper_players, force=True)  # force is overridden
    assert calls == []
    assert meta.from_cache is True
    assert len(dataset.rows) > 10


def test_offline_reports_staleness_honestly(tmp_path, fixture_fetcher, monkeypatch):
    SnapshotStore(tmp_path, fixture_fetcher).get(sleeper_players)
    meta_path = next(snap_dir(tmp_path).glob("*.meta.json"))
    meta = json.loads(meta_path.read_text())
    meta["fetched_at"] = "2020-01-01T00:00:00+00:00"  # long past any TTL
    meta_path.write_text(json.dumps(meta))

    _, result = SnapshotStore(tmp_path, fixture_fetcher, offline=True).get(sleeper_players)
    assert result.stale is True  # served, but the banner will say so


def test_health_ignores_an_unreadable_snapshot(tmp_path, fixture_fetcher):
    store = SnapshotStore(tmp_path, fixture_fetcher)
    store.get(sleeper_players)
    bad = snap_dir(tmp_path) / "29991231T235959.snap"
    bad.write_bytes(b"x")  # no sibling meta at all
    assert "sleeper_players" in store.ages()
