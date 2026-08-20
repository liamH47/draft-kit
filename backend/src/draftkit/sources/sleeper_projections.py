"""Sleeper season projections + ADP: GET api.sleeper.com/projections/nfl/{season}.

One call returns, per player, the raw projected stat line (pass_yd, rec, …)
and ADP fields per format (adp_ppr, adp_half_ppr, adp_std, adp_2qb). We keep
the RAW stat line; points are computed against league scoring at read time.
"""

import json
from datetime import timedelta
from typing import Any

from draftkit.sources.base import RawPayload, RequestSpec, SourceDataset, SourceError

TITLE = "Sleeper projections + ADP"
HOMEPAGE = "https://docs.sleeper.com/"
AUTH = "none"
ATTRIBUTION = "Projections and ADP from the public Sleeper API."
NATIVE_ID = "sleeper_id"
KIND = "projection"
PROVIDES = ["stats", "adp_ppr", "adp_half_ppr", "adp_std", "adp_2qb"]
name = "sleeper_projections"
ttl = timedelta(hours=6)

_POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")

ADP_FIELDS = ("adp_ppr", "adp_half_ppr", "adp_std", "adp_2qb")


def request(params: dict[str, Any]) -> RequestSpec:
    season = params["season"]
    positions = "&".join(f"position[]={p}" for p in _POSITIONS)
    return RequestSpec(
        url=(
            f"https://api.sleeper.com/projections/nfl/{season}"
            f"?season_type=regular&{positions}&order_by=adp_half_ppr"
        )
    )


def validate(raw: RawPayload) -> None:
    if "json" not in raw.content_type:
        raise SourceError(f"expected JSON, got {raw.content_type}")
    try:
        data = json.loads(raw.body)
    except ValueError as exc:
        raise SourceError("projections payload is not valid JSON") from exc
    if not isinstance(data, list) or len(data) < 10:
        raise SourceError("expected a non-trivial projection list")


def parse(raw: RawPayload) -> SourceDataset:
    data: list[dict[str, Any]] = json.loads(raw.body)
    rows = []
    for entry in data:
        stats = entry.get("stats") or {}
        player_id = entry.get("player_id")
        if not player_id or not stats:
            continue
        adp = {f: stats[f] for f in ADP_FIELDS if stats.get(f)}
        skip = ("adp_", "pts_", "pos_adp_", "rank_", "gp")
        stat_line = {
            k: v for k, v in stats.items() if isinstance(v, int | float) and not k.startswith(skip)
        }
        rows.append({"sleeper_id": str(player_id), "stats": stat_line, "adp": adp})
    return SourceDataset(source=name, rows=rows)
