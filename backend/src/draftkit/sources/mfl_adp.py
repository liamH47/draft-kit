"""MyFantasyLeague ADP: the home-league market, free and unauthenticated.

MFL has run hand-managed home leagues since 1999, so its drafting population
looks less like a best-ball site and more like the rooms this tool is used in.
That is the whole reason to carry a fifth market: FFC measures mock drafters,
ESPN and Yahoo measure their own platforms, and MFL measures commissioners who
set their league up by hand.

Rows are keyed on MFL's own player id, which is the FIRST column of the
DynastyProcess crosswalk we already pull, so the join costs nothing.

Docs: https://api.myfantasyleague.com/2026/api_info?STATE=details&CMD=export
"""

import json
from datetime import timedelta
from typing import Any

from draftkit.sources.base import RawPayload, RequestSpec, SourceDataset, SourceError

TITLE = "MyFantasyLeague ADP"
HOMEPAGE = "https://www.myfantasyleague.com/"
AUTH = "none"
ATTRIBUTION = "ADP data from MyFantasyLeague."
NATIVE_ID = "mfl_id"
KIND = "market"
PROVIDES = ["adp", "earliest", "latest", "times_drafted", "drafted_pct"]

name = "mfl_adp"
ttl = timedelta(hours=6)

# MFL splits its draft population by reception scoring only. There is no
# half-PPR bucket, so half-PPR reads the combined sample (-1, "any"): a wider
# and steadier population beats an exactly-matched but much thinner one, and
# reception scoring moves ADP far less than the draft pool size does.
_IS_PPR = {"standard": "0", "ppr": "1", "half_ppr": "-1"}

_URL = (
    "https://api.myfantasyleague.com/{year}/export?TYPE=adp&PERIOD=RECENT"
    "&IS_PPR={is_ppr}&IS_KEEPER=N&IS_MOCK=0&CUTOFF=5&FCOUNT=0&JSON=1"
)


def request(params: dict[str, Any]) -> RequestSpec:
    is_ppr = _IS_PPR.get(params.get("format", "half_ppr"), "-1")
    return RequestSpec(url=_URL.format(year=params["year"], is_ppr=is_ppr))


def validate(raw: RawPayload) -> None:
    try:
        data = json.loads(raw.body)
    except ValueError as exc:
        raise SourceError(f"expected JSON, got {raw.content_type}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("adp"), dict):
        raise SourceError("MFL payload has no adp block")
    if not data["adp"].get("player"):
        raise SourceError("MFL adp block carries no players")


def _number(value: Any) -> float | None:
    """MFL serves every number as a string."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse(raw: RawPayload) -> SourceDataset:
    block = json.loads(raw.body)["adp"]
    players = block["player"]
    # MFL collapses a one-row result to a bare object instead of a list. That
    # would otherwise iterate the dict's KEYS and parse nothing.
    if isinstance(players, dict):
        players = [players]

    rows = []
    for p in players:
        mfl_id = p.get("id")
        adp = _number(p.get("averagePick"))
        if not mfl_id or adp is None:
            continue
        rows.append(
            {
                "mfl_id": str(mfl_id),
                "adp": adp,
                "rank": _number(p.get("rank")),
                # Named for what they mean, not for MFL's min/max: the
                # earliest and latest pick he actually went at.
                "earliest": _number(p.get("minPick")),
                "latest": _number(p.get("maxPick")),
                "times_drafted": _number(p.get("draftsSelectedIn")),
                "drafted_pct": _number(p.get("draftSelPct")),
            }
        )
    return SourceDataset(source=name, rows=rows)
