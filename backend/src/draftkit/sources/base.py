"""Source adapter protocol.

Adapters describe HOW to fetch (request) and how to turn a raw payload into
rows (parse). They never do I/O themselves — the snapshot store fetches, so
every adapter is testable offline against a recorded fixture, and a network
outage degrades to the newest snapshot instead of a blank draft board.

Rows are keyed by the source's NATIVE id (sleeper_id, ffc name, …); identity
resolution to the canonical Sleeper player_id happens after parsing, never
inside an adapter.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Protocol


@dataclass(frozen=True)
class RequestSpec:
    url: str
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RawPayload:
    body: bytes
    content_type: str


@dataclass(frozen=True)
class SourceDataset:
    source: str
    rows: list[dict[str, Any]]


class SourceError(Exception):
    """Raised by validate() when a payload is not usable (wrong content type,
    truncated body, HTML error page from a 404, …)."""


class SourceAdapter(Protocol):
    name: str
    ttl: timedelta

    def request(self, params: dict[str, Any]) -> RequestSpec: ...

    def validate(self, raw: RawPayload) -> None: ...

    def parse(self, raw: RawPayload) -> SourceDataset: ...
