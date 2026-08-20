"""Fetch-through snapshot store: the "draft never goes blank" guarantee.

get() returns fresh data when the source cooperates, and otherwise the newest
snapshot on disk marked stale. Raw payloads are what's persisted (not parsed
rows), so parser fixes apply retroactively to old snapshots.

Layout: {root}/{adapter.name}/{params-hash}/{utc-timestamp}.snap
plus a sibling .meta.json carrying content-type and fetch time.
"""

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from draftkit.sources.base import RawPayload, RequestSpec, SourceAdapter, SourceDataset

Fetcher = Callable[[RequestSpec], RawPayload]


# Several of these feeds are ordinary websites with an API bolted on, and some
# reject clients that do not look like a browser. Identify ourselves honestly
# rather than sending httpx's default.
USER_AGENT = "draftkit/0.1 (personal fantasy draft tool)"


def http_fetch(spec: RequestSpec) -> RawPayload:
    # Tight timeouts: a slow source must degrade to the snapshot quickly
    # rather than stalling a board refresh mid-draft.
    timeout = httpx.Timeout(connect=5.0, read=8.0, write=5.0, pool=5.0)
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*", **spec.headers}
    resp = httpx.get(spec.url, headers=headers, timeout=timeout, follow_redirects=True)
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


def describe_failure(exc: BaseException) -> str:
    """Say what actually went wrong, in words worth reading at 7am on draft day.

    "fetch failed" tells nobody whether the feed is down, the season is not
    published yet, or the machine is offline — which are three different fixes.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        hint = {
            403: "the source refused us — it may be blocking non-browser clients",
            404: "no data at that URL — this season may not be published yet",
            429: "rate limited — wait a minute and retry",
        }.get(code, "unexpected status")
        return f"HTTP {code}: {hint}"
    if isinstance(exc, httpx.ConnectTimeout | httpx.ReadTimeout):
        return "timed out — the source is slow or unreachable from this network"
    if isinstance(exc, httpx.ConnectError):
        return f"could not connect — check the network or a proxy ({exc})"
    return f"{type(exc).__name__}: {exc}"


class SnapshotStore:
    def __init__(self, root: Path, fetcher: Fetcher = http_fetch, *, offline: bool = False) -> None:
        self._root = root
        self._fetch = fetcher
        self._offline = offline

    def get(
        self,
        adapter: SourceAdapter,
        params: dict[str, Any] | None = None,
        *,
        force: bool = False,
        offline: bool | None = None,
    ) -> tuple[SourceDataset, SnapshotMeta]:
        """Fresh data when the source cooperates, the newest parseable snapshot
        otherwise. This must not raise while any usable snapshot exists — it is
        the read a live draft depends on."""
        params = params or {}
        directory = self._dir(adapter, params)
        offline = self._offline if offline is None else offline

        cached = self._newest_parseable(adapter, directory)
        if cached is not None:
            dataset, fetched_at = cached
            fresh_enough = datetime.now(UTC) - fetched_at < adapter.ttl
            # Offline mode pins us to disk: during a draft a lapsed TTL must
            # never turn a board refresh into a blocking network fetch.
            if (fresh_enough and not force) or offline:
                stale = not fresh_enough
                return dataset, SnapshotMeta(adapter.name, fetched_at, stale, True)

        try:
            raw = self._fetch(adapter.request(params))
            adapter.validate(raw)
            dataset = adapter.parse(raw)  # parse BEFORE persisting, so a payload
            # that validates but cannot be parsed never poisons the newest slot
        except Exception as exc:
            if cached is None:
                raise SnapshotError(
                    f"{adapter.name}: {describe_failure(exc)} "
                    f"(and no earlier snapshot to fall back to) — {adapter.request(params).url}"
                ) from exc
            dataset, fetched_at = cached
            return dataset, SnapshotMeta(adapter.name, fetched_at, True, True)

        fetched_at = datetime.now(UTC)
        self._write(directory, raw, fetched_at)
        return dataset, SnapshotMeta(adapter.name, fetched_at, False, False)

    def ages(self) -> dict[str, float]:
        """Hours since the newest snapshot, per source dir — for /api/health."""
        out: dict[str, float] = {}
        if not self._root.is_dir():
            return out
        for source_dir in self._root.iterdir():
            # Snapshot names are UTC timestamps, so lexical order is
            # chronological order and the first readable one is the newest.
            for snap in sorted(source_dir.glob("*/*.snap"), reverse=True):
                try:
                    _, ts = self._load(snap, body=False)
                except Exception:
                    continue  # health must never fail because of a bad snapshot
                out[source_dir.name] = round((datetime.now(UTC) - ts).total_seconds() / 3600, 1)
                break
        return out

    def _dir(self, adapter: SourceAdapter, params: dict[str, Any]) -> Path:
        key = hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()[:12]
        return self._root / adapter.name / key

    def _newest_parseable(
        self, adapter: SourceAdapter, directory: Path
    ) -> tuple[SourceDataset, datetime] | None:
        """Walk snapshots newest-first and return the first one that actually
        parses. A truncated write or a since-fixed parser bug costs us one
        snapshot, not the whole cache."""
        if not directory.is_dir():
            return None
        for path in sorted(directory.glob("*.snap"), reverse=True):
            try:
                raw, fetched_at = self._load(path)
                return adapter.parse(raw), fetched_at
            except Exception:
                continue
        return None

    @staticmethod
    def _load(path: Path, body: bool = True) -> tuple[RawPayload, datetime]:
        meta = json.loads(path.with_suffix(".meta.json").read_text())
        fetched_at = datetime.fromisoformat(meta["fetched_at"])
        raw = RawPayload(body=path.read_bytes() if body else b"", content_type=meta["content_type"])
        return raw, fetched_at

    @staticmethod
    def _write(directory: Path, raw: RawPayload, fetched_at: datetime) -> None:
        """Write meta first, then the payload atomically. A snapshot is only
        discoverable once its .snap exists, so a crash mid-write leaves an
        orphan .meta.json rather than a payload with no metadata."""
        directory.mkdir(parents=True, exist_ok=True)
        stamp = fetched_at.strftime("%Y%m%dT%H%M%S")
        meta_path = directory / f"{stamp}.meta.json"
        meta_path.write_text(
            json.dumps({"fetched_at": fetched_at.isoformat(), "content_type": raw.content_type})
        )
        snap_path = directory / f"{stamp}.snap"
        tmp = snap_path.with_suffix(".snap.part")
        tmp.write_bytes(raw.body)
        os.replace(tmp, snap_path)
