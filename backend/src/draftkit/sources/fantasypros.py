"""FantasyPros expert consensus rankings (ECR): the order most rooms anchor to.

ECR is the average of a hundred-odd published experts, and it is the list a
large share of drafters — and every autodrafter walking a default board — are
actually reading. That makes it a behaviour predictor of the same kind as the
platform lists, not a value estimate; it feeds the consensus column and the
list-vs-market term, never the score.

HOW IT IS READ, and why that is worth stating plainly: FantasyPros' documented
JSON API is key-gated (api.fantasypros.com answers 403 without a partner key,
and the partners endpoint 400s), so the only route open to us is the ecrData
blob the public rankings page embeds in a <script> tag. That is a scrape of a
web page rather than a call to a published API, which has two consequences:

  1. It is more fragile than every other adapter here. A markup change breaks
     it. validate() therefore fails loudly on a page it cannot recognise,
     rather than parsing a nearly-empty list and quietly costing the column.
  2. Their terms are aimed at published aggregators. A local install reading
     this for one drafter is not that; a hosted instance serving other people
     is closer to it. See CLAUDE.md — that question is about deployment, not
     about this file, and it is not settled by the code compiling.

Joins on fantasypros_id, which the DynastyProcess crosswalk already carries —
so this is an id join for individual players, with the resolver only ever
called for team defenses.
"""

import json
import re
from datetime import timedelta
from typing import Any

from draftkit.sources.base import RawPayload, RequestSpec, SourceDataset, SourceError

TITLE = "FantasyPros expert consensus rankings"
HOMEPAGE = "https://www.fantasypros.com/nfl/rankings/"
AUTH = "none"
ATTRIBUTION = "Expert consensus rankings from FantasyPros."
NATIVE_ID = "fantasypros_id"
KIND = "expert"
PROVIDES = ["rank", "tier", "bye", "expert_rank", "expert_stdev", "expert_best", "expert_worst"]
# Params: {"format": standard|half_ppr|ppr, "superflex": bool}

name = "fantasypros"
# Twelve hours, matching the other ranking sources. ECR moves through the day
# in preseason, but a board is read against it, not traded on it.
ttl = timedelta(hours=12)

# One page per scoring format, and they are genuinely different lists — around
# 470 players sit at a different rank in standard than in half-PPR.
_URLS = {
    "standard": "https://www.fantasypros.com/nfl/rankings/consensus-cheatsheets.php",
    "half_ppr": "https://www.fantasypros.com/nfl/rankings/half-point-ppr-cheatsheets.php",
    "ppr": "https://www.fantasypros.com/nfl/rankings/ppr-cheatsheets.php",
}

# Superflex is not a scoring tweak, it is a different market. A second QB slot
# makes quarterbacks startable twice over, and the consensus reprices them
# violently: Josh Allen is ECR 1 on the superflex board and ECR 28 on the
# 1-QB board of the same date. Serving a 1-QB list into a superflex draft
# would be worse than serving no list at all, because it looks authoritative.
_SUPERFLEX_URLS = {
    "standard": "https://www.fantasypros.com/nfl/rankings/superflex-cheatsheets.php",
    "half_ppr": (
        "https://www.fantasypros.com/nfl/rankings/half-point-ppr-superflex-cheatsheets.php"
    ),
    "ppr": "https://www.fantasypros.com/nfl/rankings/ppr-superflex-cheatsheets.php",
}

# The page assigns its whole ranking payload to one variable. Non-greedy up to
# the terminating semicolon-brace, which is how the page actually writes it.
_ECR_BLOB = re.compile(r"var\s+ecrData\s*=\s*(\{.*?\});", re.S)

# FantasyPros spells team defenses DST; everything else already matches ours.
_POSITIONS = {"DST": "DEF"}


def request(params: dict[str, Any]) -> RequestSpec:
    urls = _SUPERFLEX_URLS if params.get("superflex") else _URLS
    return RequestSpec(url=urls[params.get("format", "half_ppr")])


def _blob(raw: RawPayload) -> dict[str, Any]:
    """Pull the ranking payload out of the page, or say why it is not there.

    Every failure here means the page changed shape. Naming which part failed
    is the difference between a five-minute fix and an evening of guessing.
    """
    match = _ECR_BLOB.search(raw.body.decode("utf-8", "replace"))
    if match is None:
        raise SourceError("no ecrData block on the FantasyPros rankings page")
    try:
        data = json.loads(match.group(1))
    except ValueError as exc:
        raise SourceError("the FantasyPros ecrData block is not valid JSON") from exc
    if not isinstance(data, dict) or not data.get("players"):
        raise SourceError("the FantasyPros ecrData block holds no players")
    return data


def validate(raw: RawPayload) -> None:
    if "html" not in raw.content_type:
        raise SourceError(f"expected HTML, got {raw.content_type}")
    _blob(raw)


def _number(value: Any) -> float | None:
    """ECR reports its spread as strings, and empties them for a player only
    one expert ranked. Absent beats zero: zero is a real rank."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse(raw: RawPayload) -> SourceDataset:
    data = _blob(raw)
    rows = []
    for p in data["players"]:
        if not p.get("player_id") or not p.get("rank_ecr"):
            continue
        position = p.get("player_position_id") or ""
        rows.append(
            {
                "fantasypros_id": str(p["player_id"]),
                "name": p.get("player_name") or "",
                "position": _POSITIONS.get(position, position),
                "team": p.get("player_team_id") or None,
                "rank": float(p["rank_ecr"]),
                "tier": int(p["tier"]) if p.get("tier") else None,
                "bye": int(p["player_bye_week"]) if p.get("player_bye_week") else None,
                # The spread across the experts who ranked him. A wide one is a
                # player the industry disagrees about, which is worth seeing
                # next to a confident-looking average.
                "expert_rank": _number(p.get("rank_ave")),
                "expert_stdev": _number(p.get("rank_std")),
                "expert_best": _number(p.get("rank_min")),
                "expert_worst": _number(p.get("rank_max")),
            }
        )
    return SourceDataset(source=name, rows=rows)
