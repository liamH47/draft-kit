"""Fetch-through snapshot store: the "draft never goes blank" guarantee.

get() returns fresh data when the source cooperates, and otherwise the newest
snapshot on disk marked stale. Raw payloads are what's persisted (not parsed
rows), so parser fixes apply retroactively to old snapshots.

Layout: {root}/{adapter.name}/{params-hash}/{utc-timestamp}.snap
plus a sibling .meta.json carrying content-type and fetch time.
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from draftkit.sources.base import RawPayload, RequestSpec, SourceAdapter, SourceDataset

Fetcher = Callable[[RequestSpec], RawPayload]


def http_fetch(spec: RequestSpec) -> RawPayload:
    resp = httpx.get(spec.url, headers=spec.headers, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    return RawPayload(body=resp.content, content_type=resp.headers.get("content-type", ""))


@dataclass(frozen=True)
class SnapshotMeta:
    source: str
    fetched_at: datetime
    stale: bool
    from_cache: bool


class SnapshotError(Exception):
    """No fresh fetch possible and no snapshot on disk to fall back to."""


class SnapshotStore:
    def __init__(self, root: Path, fetcher: Fetcher = http_fetch) -> None:
        self._root = root
        self._fetch = fetcher

    def get(
        self, adapter: SourceAdapter, params: dict[str, Any] | None = None, *, force: bool = False
    ) -> tuple[SourceDataset, SnapshotMeta]:
        params = params or {}
        directory = self._dir(adapter, params)
        newest = self._newest(directory)

        if newest is not None and not force:
            raw, fetched_at = self._load(newest)
            age_ok = datetime.now(UTC) - fetched_at < adapter.ttl
            if age_ok:
                return adapter.parse(raw), SnapshotMeta(adapter.name, fetched_at, False, True)

        try:
            raw = self._fetch(adapter.request(params))
            adapter.validate(raw)
        except Exception as exc:
            if newest is None:
                raise SnapshotError(f"{adapter.name}: fetch failed and no snapshot exists") from exc
            raw, fetched_at = self._load(newest)
            return adapter.parse(raw), SnapshotMeta(adapter.name, fetched_at, True, True)

        fetched_at = datetime.now(UTC)
        self._write(directory, raw, fetched_at)
        return adapter.parse(raw), SnapshotMeta(adapter.name, fetched_at, False, False)

    def ages(self) -> dict[str, float]:
        """Hours since the newest snapshot, per source dir — for /api/health."""
        out: dict[str, float] = {}
        if not self._root.is_dir():
            return out
        for source_dir in self._root.iterdir():
            newest_ts: datetime | None = None
            for snap in source_dir.glob("*/*.snap"):
                _, ts = self._load(snap, body=False)
                if newest_ts is None or ts > newest_ts:
                    newest_ts = ts
            if newest_ts is not None:
                out[source_dir.name] = round(
                    (datetime.now(UTC) - newest_ts).total_seconds() / 3600, 1
                )
        return out

    def _dir(self, adapter: SourceAdapter, params: dict[str, Any]) -> Path:
        key = hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()[:12]
        return self._root / adapter.name / key

    @staticmethod
    def _newest(directory: Path) -> Path | None:
        if not directory.is_dir():
            return None
        snaps = sorted(directory.glob("*.snap"))
        return snaps[-1] if snaps else None

    @staticmethod
    def _load(path: Path, body: bool = True) -> tuple[RawPayload, datetime]:
        meta = json.loads(path.with_suffix(".meta.json").read_text())
        fetched_at = datetime.fromisoformat(meta["fetched_at"])
        raw = RawPayload(body=path.read_bytes() if body else b"", content_type=meta["content_type"])
        return raw, fetched_at

    @staticmethod
    def _write(directory: Path, raw: RawPayload, fetched_at: datetime) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        stamp = fetched_at.strftime("%Y%m%dT%H%M%S")
        (directory / f"{stamp}.snap").write_bytes(raw.body)
        (directory / f"{stamp}.meta.json").write_text(
            json.dumps({"fetched_at": fetched_at.isoformat(), "content_type": raw.content_type})
        )
