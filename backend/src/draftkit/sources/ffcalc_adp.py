"""Fantasy Football Calculator ADP: real human mock drafts, by format and size.

https://help.fantasyfootballcalculator.com/article/42-adp-rest-api
Free for use with attribution (linked in the app footer and README).
"""

import json
from datetime import timedelta
from typing import Any

from draftkit.sources.base import RawPayload, RequestSpec, SourceDataset, SourceError

TITLE = "Fantasy Football Calculator ADP"
HOMEPAGE = "https://fantasyfootballcalculator.com/adp"
AUTH = "none"
ATTRIBUTION = "ADP data from Fantasy Football Calculator."
NATIVE_ID = "ffc_id"
KIND = "market"
PROVIDES = ["adp", "stdev", "high", "low", "times_drafted", "bye"]
name = "ffcalc"
ttl = timedelta(hours=3)

# draftkit scoring preset -> FFC format path segment
FORMATS = {"standard": "standard", "half_ppr": "half-ppr", "ppr": "ppr", "2qb": "2qb"}


def request(params: dict[str, Any]) -> RequestSpec:
    fmt = FORMATS[params.get("format", "half_ppr")]
    teams = params.get("teams", 12)
    year = params["year"]
    return RequestSpec(
        url=f"https://fantasyfootballcalculator.com/api/v1/adp/{fmt}?teams={teams}&year={year}"
    )


def validate(raw: RawPayload) -> None:
    if "json" not in raw.content_type:
        raise SourceError(f"expected JSON, got {raw.content_type}")
    data = json.loads(raw.body)
    if data.get("status") != "Success" or not data.get("players"):
        raise SourceError("FFC response missing status/players")


def parse(raw: RawPayload) -> SourceDataset:
    data = json.loads(raw.body)
    meta = data.get("meta", {})
    rows = []
    for p in data["players"]:
        rows.append(
            {
                "ffc_id": p.get("player_id"),
                "name": p["name"],
                "position": "DEF" if p.get("position") == "DST" else p.get("position"),
                "team": p.get("team"),
                "adp": p.get("adp"),
                "stdev": p.get("stdev"),
                "high": p.get("high"),
                "low": p.get("low"),
                "bye": p.get("bye"),
                "times_drafted": p.get("times_drafted"),
                "total_drafts": meta.get("total_drafts"),
            }
        )
    return SourceDataset(source=name, rows=rows)
