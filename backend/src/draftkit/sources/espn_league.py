"""Read an ESPN league's own settings, so nobody has to retype them.

Getting roster slots wrong silently mis-prices every player at the affected
position — a 3-WR league scored as 2-WR moves replacement level by a dozen
players. The league itself knows the answer, so ask it rather than asking the
user to transcribe it.

Public leagues need nothing. Private leagues need the two cookies ESPN sets in
your browser (espn_s2 and SWID); put them in .env as DRAFTKIT_ESPN_S2 and
DRAFTKIT_ESPN_SWID. They are credentials — never paste them into a chat, a
commit, or a log.

Note: this reads *settings*, which are static. ESPN exposes no live draft feed
(picks only appear once a draft is complete), so live sync there needs a
browser extension. That is a separate job.
"""

import json
from datetime import timedelta
from typing import Any

from draftkit.sources.base import RawPayload, RequestSpec, SourceDataset, SourceError

TITLE = "ESPN league settings"
HOMEPAGE = "https://fantasy.espn.com/"
AUTH = "none"  # cookies only for private leagues
ATTRIBUTION = "League settings from ESPN Fantasy."
NATIVE_ID = "espn_league_id"
KIND = "league"
PROVIDES = ["num_teams", "roster", "scoring_preset", "rounds", "reception_points"]

name = "espn_league"
ttl = timedelta(hours=12)

_URL = (
    "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}"
    "/segments/0/leagues/{league_id}"
)

# ESPN lineup slot ids -> our roster fields. Slots we do not model (IR, taxi)
# are deliberately absent rather than mapped to something approximate.
_SLOT_MAP = {
    0: "qb",
    2: "rb",
    4: "wr",
    6: "te",
    16: "dst",
    17: "k",
    20: "bench",
    23: "flex",  # RB/WR/TE
    7: "superflex",  # ESPN calls it OP: any offensive player, in practice a QB
}

# ESPN scoring item id for a reception. Its point value is what separates
# standard from half-PPR from full PPR, which is the one scoring fact that
# changes rankings the most.
_RECEPTION_STAT_ID = 53


def request(params: dict[str, Any]) -> RequestSpec:
    headers = {}
    espn_s2 = params.get("espn_s2")
    swid = params.get("swid")
    if espn_s2 and swid:
        headers["Cookie"] = f"espn_s2={espn_s2}; SWID={swid}"
    return RequestSpec(
        url=_URL.format(season=params["season"], league_id=params["league_id"]) + "?view=mSettings",
        headers=headers,
    )


def validate(raw: RawPayload) -> None:
    if "json" not in raw.content_type:
        raise SourceError(f"expected JSON, got {raw.content_type}")
    try:
        data = json.loads(raw.body)
    except ValueError as exc:
        raise SourceError("ESPN league payload is not valid JSON") from exc
    if not isinstance(data, dict) or "settings" not in data:
        raise SourceError("ESPN league payload has no settings — is the league private?")


def _reception_points(settings: dict[str, Any]) -> float:
    items = (settings.get("scoringSettings") or {}).get("scoringItems") or []
    for item in items:
        if item.get("statId") == _RECEPTION_STAT_ID:
            return float(item.get("points", 0.0))
    return 0.0


def _scoring_preset(reception_points: float) -> str:
    if reception_points >= 0.75:
        return "ppr"
    if reception_points >= 0.25:
        return "half_ppr"
    return "standard"


def parse(raw: RawPayload) -> SourceDataset:
    data = json.loads(raw.body)
    settings = data["settings"]
    roster_settings = settings.get("rosterSettings") or {}
    slot_counts = roster_settings.get("lineupSlotCounts") or {}

    roster: dict[str, int] = {}
    for slot_id, count in slot_counts.items():
        field = _SLOT_MAP.get(int(slot_id))
        if field and count:
            roster[field] = roster.get(field, 0) + int(count)

    reception_points = _reception_points(settings)
    draft_settings = settings.get("draftSettings") or {}
    num_teams = int(settings.get("size") or 0)
    starters = sum(v for k, v in roster.items() if k != "bench")
    rounds = starters + roster.get("bench", 0)

    return SourceDataset(
        source=name,
        rows=[
            {
                "espn_league_id": str(data.get("id", "")),
                "league_name": settings.get("name") or "ESPN league",
                "num_teams": num_teams,
                "roster": roster,
                "reception_points": reception_points,
                "scoring_preset": _scoring_preset(reception_points),
                # A full draft takes exactly as many rounds as there are roster
                # spots, which ESPN does not state directly.
                "rounds": rounds,
                "draft_type": draft_settings.get("type"),
            }
        ],
    )
