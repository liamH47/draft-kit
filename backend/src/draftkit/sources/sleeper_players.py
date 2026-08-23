"""Sleeper player universe: GET api.sleeper.app/v1/players/nfl.

~5MB payload mapping player_id -> player object. Sleeper asks that this be
cached and fetched at most daily.
"""

import json
from datetime import timedelta
from typing import Any

from draftkit.models.player import FANTASY_POSITIONS
from draftkit.sources.base import RawPayload, RequestSpec, SourceDataset, SourceError

TITLE = "Sleeper player universe"
HOMEPAGE = "https://docs.sleeper.com/"
AUTH = "none"
ATTRIBUTION = "Player data from the public Sleeper API."
NATIVE_ID = "sleeper_id"
KIND = "identity"
PROVIDES = ["name", "position", "team", "status", "injury_status", "depth_chart_order"]
name = "sleeper_players"
ttl = timedelta(hours=24)


def request(params: dict[str, Any]) -> RequestSpec:
    return RequestSpec(url="https://api.sleeper.app/v1/players/nfl")


def validate(raw: RawPayload) -> None:
    if "json" not in raw.content_type:
        raise SourceError(f"expected JSON, got {raw.content_type}")
    try:
        data = json.loads(raw.body)
    except ValueError as exc:
        raise SourceError("players payload is not valid JSON") from exc
    if not isinstance(data, dict) or len(data) < 10:
        raise SourceError("players payload is not a non-trivial id->player mapping")


def parse(raw: RawPayload) -> SourceDataset:
    data: dict[str, dict[str, Any]] = json.loads(raw.body)
    rows = []
    for player_id, p in data.items():
        position = p.get("position")
        if position not in FANTASY_POSITIONS:
            continue
        # Team defenses come through with player_id == team abbreviation and
        # position DEF; they have no full_name.
        fallback = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
        player_name = p.get("full_name") or fallback
        if not player_name:
            continue
        rows.append(
            {
                "sleeper_id": player_id,
                "name": player_name,
                "position": position,
                "team": p.get("team"),
                "status": p.get("status"),
                "active": p.get("active", False),
                # Already inside the payload we download daily, and until now
                # thrown away: whether he is hurt, how badly, and where he sits
                # on his own depth chart. A board that recommends a man on IR
                # is wrong in the way that costs a season.
                "injury_status": p.get("injury_status"),
                "injury_body_part": p.get("injury_body_part"),
                "depth_chart_order": p.get("depth_chart_order"),
            }
        )
    return SourceDataset(source=name, rows=rows)
