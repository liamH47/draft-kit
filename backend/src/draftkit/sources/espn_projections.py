"""ESPN 2026 season projections: the second projection source.

With only one projection source (Sleeper) nothing can cross-check a weird
number — Drake Maye projected as QB3 is either an edge or a bug, and one
source cannot tell you which. ESPN serves full-season projections with RAW
stat categories on the same openly-served host as espn_market, so points are
computed under the user's actual league scoring, not ESPN's default.

Undocumented endpoint: no stability guarantee; every consumer treats it as
optional, and the board reads the snapshot on draft night.
"""

import json
from datetime import timedelta
from typing import Any

from draftkit.sources.base import RawPayload, RequestSpec, SourceDataset, SourceError

TITLE = "ESPN season projections"
HOMEPAGE = "https://fantasy.espn.com/"
AUTH = "none"
ATTRIBUTION = "Season projections from ESPN Fantasy."
NATIVE_ID = "espn_id"
KIND = "projection"
PROVIDES = ["stats", "applied_total"]

name = "espn_projections"
ttl = timedelta(hours=6)

_URL = (
    "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}"
    "/segments/0/leaguedefaults/3?view=kona_player_info"
)

_POSITION_BY_ID = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DEF"}

# ESPN stat category id -> the Sleeper stat name our scoring weights use.
# Only scoring-relevant categories are mapped; a position that maps to nothing
# (DEF) falls back to ESPN's own applied total. The under-40 field-goal bucket
# maps to fgm_30_39 because the 0-19/20-29/30-39 weights are identical in
# every standard ruleset.
_STAT_MAP = {
    "3": "pass_yd",
    "4": "pass_td",
    "19": "pass_2pt",
    "20": "pass_int",
    "24": "rush_yd",
    "25": "rush_td",
    "26": "rush_2pt",
    "42": "rec_yd",
    "43": "rec_td",
    "44": "rec_2pt",
    "53": "rec",
    "72": "fum_lost",
    "74": "fgm_50p",
    "77": "fgm_40_49",
    "80": "fgm_30_39",
    "85": "fgmiss",
    "86": "xpm",
    # First downs. ESPN publishes these and we were dropping them, which cost
    # nothing until a league actually scored them — and then it cost a great
    # deal quietly, because points here are the MEAN of Sleeper and ESPN. In a
    # league paying a point per rushing and receiving first down, every back
    # was landing ~50 points light (half of the ~100 he earns), every receiver
    # ~38 light, and quarterbacks only ~18 — a systematic tilt AGAINST exactly
    # the positions the rule rewards. Verified against ESPN's own league UI:
    # id 211 is Josh Allen's 188 passing first downs to the decimal.
    #
    # pass_fd is mapped but carries no default weight, because ESPN's own
    # projected totals show it is not scored (Matthew Stafford's 204 passing
    # first downs would put him 200 points above the number ESPN displays).
    # A league that does score it now only has to set the weight.
    "211": "pass_fd",
    "212": "rush_fd",
    "213": "rec_fd",
}


def request(params: dict[str, Any]) -> RequestSpec:
    season = params["season"]
    limit = params.get("limit", 600)
    # Without a parseable filter ESPN silently ignores the view and returns a
    # bare all-player list with no stats — validate() guards for that shape.
    fantasy_filter = json.dumps(
        {
            "players": {
                "limit": limit,
                "sortDraftRanks": {"sortPriority": 100, "sortAsc": True, "value": "STANDARD"},
            }
        }
    )
    return RequestSpec(
        url=_URL.format(season=season),
        headers={"X-Fantasy-Filter": fantasy_filter},
    )


def validate(raw: RawPayload) -> None:
    if "json" not in raw.content_type:
        raise SourceError(f"expected JSON, got {raw.content_type}")
    try:
        data = json.loads(raw.body)
    except ValueError as exc:
        raise SourceError("ESPN projections payload is not valid JSON") from exc
    # A bare list means the filter header was ignored: no stats, useless.
    if not isinstance(data, dict) or not data.get("players"):
        raise SourceError("ESPN projections payload has no players — was the filter ignored?")


def _season_projection(player: dict[str, Any]) -> dict[str, Any] | None:
    """statSourceId 1 is a projection (0 is actuals) and statSplitTypeId 0 is
    the full season (1 is weekly). Newest season wins if several are present."""
    candidates = [
        entry
        for entry in player.get("stats") or []
        if entry.get("statSourceId") == 1 and entry.get("statSplitTypeId") == 0
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda entry: entry.get("seasonId") or 0)


def parse(raw: RawPayload) -> SourceDataset:
    data = json.loads(raw.body)
    rows = []
    for entry in data["players"]:
        player = entry.get("player") or entry
        position = _POSITION_BY_ID.get(player.get("defaultPositionId"))
        if position is None:
            continue
        projection = _season_projection(player)
        if projection is None:
            continue
        raw_stats = projection.get("stats") or {}
        stats = {
            _STAT_MAP[k]: float(v)
            for k, v in raw_stats.items()
            if k in _STAT_MAP and isinstance(v, int | float)
        }
        rows.append(
            {
                "espn_id": str(entry.get("id") or player.get("id")),
                "name": player.get("fullName") or "",
                "position": position,
                "team": None,  # numeric team ids; the crosswalk joins by espn_id
                "stats": stats,
                # ESPN's own scored total (their default PPR rules) — the
                # fallback for positions the stat map does not cover.
                "applied_total": projection.get("appliedTotal"),
            }
        )
    return SourceDataset(source=name, rows=rows)
