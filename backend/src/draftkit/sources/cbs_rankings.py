"""CBS consensus rankings: the editorial order CBS autodrafters walk.

CBS's documented public fantasy API answers its rankings endpoint without a
token. Only rankings are open (their projections and ADP endpoints 500), so
this source contributes a ranking list and a bye week, nothing more — which
is exactly what the consensus column and the list-vs-market term want.
"""

import json
from datetime import timedelta
from typing import Any

from draftkit.sources.base import RawPayload, RequestSpec, SourceDataset, SourceError

TITLE = "CBS consensus rankings"
HOMEPAGE = "https://www.cbssports.com/fantasy/football/"
AUTH = "none"
ATTRIBUTION = "Rankings from CBS Sports Fantasy."
NATIVE_ID = "cbs_id"
KIND = "platform"
PROVIDES = ["rank", "bye"]

name = "cbs_rankings"
ttl = timedelta(hours=12)

# CBS publishes PPR and standard averages; half-PPR rooms read the PPR list,
# which is what CBS itself shows those leagues.
_SOURCES = {"ppr": "cbs_avg_ppr", "half_ppr": "cbs_avg_ppr", "standard": "cbs_avg_standard"}

_URL = (
    "https://api.cbssports.com/fantasy/players/rankings"
    "?version=3.0&SPORT=football&type=overall&source={source}&response_format=JSON"
)


def request(params: dict[str, Any]) -> RequestSpec:
    source = _SOURCES[params.get("format", "ppr")]
    return RequestSpec(url=_URL.format(source=source))


def validate(raw: RawPayload) -> None:
    if "json" not in raw.content_type:
        raise SourceError(f"expected JSON, got {raw.content_type}")
    try:
        data = json.loads(raw.body)
    except ValueError as exc:
        raise SourceError("CBS rankings payload is not valid JSON") from exc
    players = (data.get("body") or {}).get("rankings", {}) if isinstance(data, dict) else {}
    if not isinstance(players, dict) or not players.get("players"):
        raise SourceError("CBS rankings payload has no players")


def parse(raw: RawPayload) -> SourceDataset:
    data = json.loads(raw.body)
    rows = []
    for p in data["body"]["rankings"]["players"]:
        if not p.get("id") or not p.get("rank"):
            continue
        rows.append(
            {
                "cbs_id": str(p["id"]),
                "name": p.get("fullname") or "",
                "position": "DEF" if p.get("position") == "DST" else p.get("position"),
                "team": p.get("pro_team"),
                "rank": float(p["rank"]),
                "bye": int(p["bye_week"]) if p.get("bye_week") else None,
            }
        )
    return SourceDataset(source=name, rows=rows)
