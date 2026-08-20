"""Boris Chen expert tiers (GMM clusters over FantasyPros ranks), public S3 CSVs.

http://www.borischen.co/ — credit shown in the app.
Suffix encodes scoring: "" = standard, -HALF, -PPR.
"""

import csv
import io
from datetime import timedelta
from typing import Any

from draftkit.sources.base import RawPayload, RequestSpec, SourceDataset, SourceError

TITLE = "Boris Chen expert tiers"
HOMEPAGE = "http://www.borischen.co/"
AUTH = "none"
ATTRIBUTION = "Tier data by Boris Chen."
NATIVE_ID = "name"
KIND = "expert"
PROVIDES = ["tier", "rank", "expert_rank", "expert_stdev", "expert_best", "expert_worst"]
name = "borischen"
ttl = timedelta(hours=12)

_SUFFIX = {"standard": "", "half_ppr": "-HALF-PPR", "ppr": "-PPR"}


def request(params: dict[str, Any]) -> RequestSpec:
    suffix = _SUFFIX[params.get("format", "half_ppr")]
    return RequestSpec(url=f"https://s3-us-west-1.amazonaws.com/fftiers/out/weekly-ALL{suffix}.csv")


def validate(raw: RawPayload) -> None:
    head = raw.body[:200].decode("utf-8", errors="replace")
    if "Player.Name" not in head or "Tier" not in head:
        raise SourceError(f"unexpected tiers CSV header: {head[:80]!r}")


def _number(value: str | None) -> float | None:
    """Columns come and go between Boris Chen's files; absence is not failure."""
    try:
        return float(value) if value not in (None, "", "NA") else None
    except ValueError:
        return None


def parse(raw: RawPayload) -> SourceDataset:
    reader = csv.DictReader(io.StringIO(raw.body.decode("utf-8")))
    rows = []
    for r in reader:
        rows.append(
            {
                "name": r["Player.Name"],
                "position": "DEF" if r.get("Position") == "DST" else r.get("Position"),
                "tier": int(r["Tier"]),
                "rank": int(r["Rank"]),
                # Expert consensus and the spread of disagreement. The spread
                # matters as much as the rank: a boundary the experts argue
                # about is not really a boundary.
                "expert_rank": _number(r.get("Avg.Rank")),
                "expert_stdev": _number(r.get("Std.Dev")),
                "expert_best": _number(r.get("Best.Rank")),
                "expert_worst": _number(r.get("Worst.Rank")),
            }
        )
    return SourceDataset(source=name, rows=rows)
