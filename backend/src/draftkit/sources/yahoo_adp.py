"""Yahoo draft analysis: ADP, auction cost and percent drafted, no OAuth.

Yahoo's official API is OAuth-gated, but their read-only public host
(pub-api-ro.fantasysports.yahoo.com) serves the same fantasy v2 draft
analysis openly. For a user who actually drafts on Yahoo this is the real
room's price, not a proxy.

Pages are capped at 25 players and ADP decays to a "-" sentinel past the
top ~275, so the pool walks pages until a page carries no ADP at all.
Undocumented host, owes us nothing: snapshot-and-fallback is mandatory and
the board reads the snapshot on draft night.
"""

import json
from datetime import timedelta
from typing import Any

from draftkit.sources.base import RawPayload, RequestSpec, SourceDataset, SourceError

TITLE = "Yahoo draft analysis"
HOMEPAGE = "https://football.fantasysports.yahoo.com/"
AUTH = "none"
ATTRIBUTION = "ADP and draft analysis from Yahoo Fantasy Sports."
NATIVE_ID = "yahoo_id"
KIND = "platform"
PROVIDES = ["adp", "average_round", "average_cost", "percent_drafted", "bye"]

name = "yahoo_adp"
ttl = timedelta(hours=6)

PAGE_SIZE = 25  # Yahoo's hard cap per request

_URL = (
    "https://pub-api-ro.fantasysports.yahoo.com/fantasy/v2/game/nfl"
    "/players;start={start};count={count};sort=AR/draft_analysis?format=json"
)


def request(params: dict[str, Any]) -> RequestSpec:
    start = params.get("start", 0)
    return RequestSpec(url=_URL.format(start=start, count=PAGE_SIZE))


def validate(raw: RawPayload) -> None:
    if "json" not in raw.content_type:
        raise SourceError(f"expected JSON, got {raw.content_type}")
    try:
        data = json.loads(raw.body)
    except ValueError as exc:
        raise SourceError("Yahoo payload is not valid JSON") from exc
    if not isinstance(data, dict) or "fantasy_content" not in data:
        raise SourceError("Yahoo payload has no fantasy_content")


def _fold(fragments: list) -> dict[str, Any]:
    """Yahoo's format: a list of single-key dicts (with stray non-dicts).
    Fold it into one plain dict."""
    out: dict[str, Any] = {}
    for fragment in fragments:
        if isinstance(fragment, dict):
            out.update(fragment)
    return out


def _number(value: Any) -> float | None:
    """Yahoo serves every number as a string and '-' for 'no data'."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse(raw: RawPayload) -> SourceDataset:
    data = json.loads(raw.body)
    game = data["fantasy_content"].get("game") or []
    players_map: dict[str, Any] = {}
    for part in game:
        if isinstance(part, dict) and "players" in part:
            players_map = part["players"]
            break

    rows = []
    for key, wrapped in players_map.items():
        if key == "count" or not isinstance(wrapped, dict):
            continue
        player = wrapped.get("player") or []
        identity = _fold(player[0]) if player and isinstance(player[0], list) else {}
        analysis = _fold(_fold(player[1:]).get("draft_analysis") or [])

        yahoo_id = identity.get("player_id")
        full_name = (identity.get("name") or {}).get("full")
        if not yahoo_id or not full_name:
            continue
        position = (identity.get("display_position") or "").split(",")[0].strip()
        bye = _number((identity.get("bye_weeks") or {}).get("week"))
        rows.append(
            {
                "yahoo_id": str(yahoo_id),
                "name": full_name,
                "position": position,
                "team": identity.get("editorial_team_abbr"),
                "adp": _number(analysis.get("average_pick")),
                "average_round": _number(analysis.get("average_round")),
                "average_cost": _number(analysis.get("average_cost")),
                "percent_drafted": _number(analysis.get("percent_drafted")),
                "bye": int(bye) if bye else None,
            }
        )
    return SourceDataset(source=name, rows=rows)
