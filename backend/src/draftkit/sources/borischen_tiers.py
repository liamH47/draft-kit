"""Boris Chen expert tiers (GMM clusters over FantasyPros ranks), public S3 CSVs.

http://www.borischen.co/ — credit shown in the app.
Suffix encodes scoring: "" = standard, -HALF, -PPR.
"""

import csv
import io
from datetime import timedelta
from typing import Any

from draftkit.sources.base import RawPayload, RequestSpec, SourceDataset, SourceError

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
            }
        )
    return SourceDataset(source=name, rows=rows)
