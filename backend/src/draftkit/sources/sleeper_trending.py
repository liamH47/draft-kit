"""Sleeper trending adds and drops: what the rooms are reacting to right now.

/v1/players/nfl/trending/{add|drop} returns how many Sleeper leagues added or
dropped a player inside a lookback window. Waiver churn moves within hours of
news breaking; ADP takes days to reprice, and a ranking list takes until
somebody publishes a new one. This is the fastest signal the app carries that
a player's situation has changed.

It is buzz, not value, and it never touches the recommendation score. Adds
follow news, and news is not always good news for the man being added — the
back-up who trends after a starter tears an ACL is the same shape on this feed
as a breakout. It exists so that a name whose world changed since the last ADP
reading is visible on the board rather than silently stale.

Docs: https://docs.sleeper.com/#trending-players
"""

import json
from datetime import timedelta
from typing import Any

from draftkit.sources.base import RawPayload, RequestSpec, SourceDataset, SourceError

TITLE = "Sleeper trending players"
HOMEPAGE = "https://docs.sleeper.com/#trending-players"
AUTH = "none"
ATTRIBUTION = "Trending add/drop counts from the public Sleeper API."
NATIVE_ID = "sleeper_id"
KIND = "buzz"
PROVIDES = ["trend_count"]

name = "sleeper_trending"
# Short: the entire point of this source is that it is fresher than ADP.
ttl = timedelta(hours=3)

# Sleeper caps the response at 100 rows however large a limit you ask for.
PAGE_LIMIT = 100

_KINDS = ("add", "drop")

_URL = "https://api.sleeper.app/v1/players/nfl/trending/{kind}?lookback_hours={hours}&limit={limit}"


def request(params: dict[str, Any]) -> RequestSpec:
    kind = params.get("kind", "add")
    if kind not in _KINDS:
        raise ValueError(f"trending kind must be one of {_KINDS}, got {kind!r}")
    hours = params.get("lookback_hours", 24)
    return RequestSpec(url=_URL.format(kind=kind, hours=hours, limit=PAGE_LIMIT))


def validate(raw: RawPayload) -> None:
    if "json" not in raw.content_type:
        raise SourceError(f"expected JSON, got {raw.content_type}")
    try:
        data = json.loads(raw.body)
    except ValueError as exc:
        raise SourceError("trending payload is not valid JSON") from exc
    if not isinstance(data, list) or not data:
        raise SourceError("trending payload is not a non-empty list")


def parse(raw: RawPayload) -> SourceDataset:
    data = json.loads(raw.body)
    rows = []
    for entry in data:
        player_id = entry.get("player_id")
        count = entry.get("count")
        if not player_id or not isinstance(count, int | float):
            continue
        rows.append({"sleeper_id": str(player_id), "trend_count": int(count)})
    return SourceDataset(source=name, rows=rows)
