"""ESPN player data: the platform's own ADP and its own ranking list.

This is the source that makes market-vs-list comparison honest. Both numbers
come from the same population, so their difference is not one pundit's opinion
differenced against another's — it is "where this platform's list puts him"
against "where this platform's drafters actually take him".

  ownership.averageDraftPosition  -> real ESPN ADP
  draftRanksByRankType[*].rank    -> the editorial list ESPN shows in the draft
                                     room, and the order its autodrafters walk

The rank list is known to diverge sharply from actual ADP. That divergence is
the signal, not a defect — but it is why the rank must never be used as a value
estimate, only as a predictor of behaviour.

Undocumented endpoint: no developer programme, no stability guarantee. It is
isolated behind this adapter and every consumer treats it as optional.
"""

import json
from datetime import timedelta
from typing import Any

from draftkit.sources.base import RawPayload, RequestSpec, SourceDataset, SourceError

TITLE = "ESPN ADP and draft ranks"
HOMEPAGE = "https://fantasy.espn.com/"
AUTH = "none"
ATTRIBUTION = "ADP and draft ranks from ESPN Fantasy."
NATIVE_ID = "espn_id"
KIND = "platform"
PROVIDES = ["adp", "auction_value", "percent_owned", "list_rank"]

name = "espn_market"
ttl = timedelta(hours=6)

_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/players"

# ESPN's position ids. Anything else is not a fantasy position for our purposes.
_POSITION_BY_ID = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DEF"}

# Which rank list to prefer. PPR and STANDARD are the two ESPN publishes; they
# are frequently identical, which is itself worth knowing.
_RANK_TYPES = ("PPR", "STANDARD")


def request(params: dict[str, Any]) -> RequestSpec:
    season = params["season"]
    limit = params.get("limit", 700)
    # Without the filter header ESPN caps the response at 50 rows.
    fantasy_filter = json.dumps(
        {"players": {"limit": limit, "sortPercOwned": {"sortAsc": False, "sortPriority": 1}}}
    )
    return RequestSpec(
        url=_URL.format(season=season) + "?view=kona_player_info",
        headers={"X-Fantasy-Filter": fantasy_filter},
    )


def validate(raw: RawPayload) -> None:
    if "json" not in raw.content_type:
        raise SourceError(f"expected JSON, got {raw.content_type}")
    try:
        data = json.loads(raw.body)
    except ValueError as exc:
        raise SourceError("ESPN payload is not valid JSON") from exc
    if not isinstance(data, list) or len(data) < 10:
        raise SourceError("expected a non-trivial ESPN player list")


def _list_rank(player: dict[str, Any]) -> float | None:
    ranks = player.get("draftRanksByRankType") or {}
    for rank_type in _RANK_TYPES:
        entry = ranks.get(rank_type)
        if isinstance(entry, dict) and entry.get("rank"):
            return float(entry["rank"])
    return None


def parse(raw: RawPayload) -> SourceDataset:
    data: list[dict[str, Any]] = json.loads(raw.body)
    rows = []
    for entry in data:
        player = entry.get("player") or entry
        position = _POSITION_BY_ID.get(player.get("defaultPositionId"))
        if position is None:
            continue
        ownership = player.get("ownership") or {}
        adp = ownership.get("averageDraftPosition")
        rows.append(
            {
                "espn_id": str(entry.get("id") or player.get("id")),
                "name": player.get("fullName") or "",
                "position": position,
                # ESPN team ids are numeric; the crosswalk joins on espn_id, so
                # we deliberately do not guess an abbreviation here.
                "team": None,
                # Live market: where ESPN drafters actually take him.
                "adp": float(adp) if adp else None,
                "auction_value": ownership.get("auctionValueAverage"),
                "percent_owned": ownership.get("percentOwned"),
                # The list: what the draft room shows and autodrafters follow.
                "list_rank": _list_rank(player),
            }
        )
    return SourceDataset(source=name, rows=rows)
