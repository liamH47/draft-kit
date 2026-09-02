"""DynastyProcess cross-platform player ID map (sleeper/espn/yahoo/…).

https://github.com/dynastyprocess/data — the join utility that saves us from
name-matching hell across sources and, later, across draft platforms.
"""

import csv
import io
from datetime import timedelta
from typing import Any

from draftkit.sources.base import RawPayload, RequestSpec, SourceDataset, SourceError

TITLE = "DynastyProcess ID crosswalk"
HOMEPAGE = "https://github.com/dynastyprocess/data"
AUTH = "none"
ATTRIBUTION = "Player ID crosswalk from DynastyProcess."
NATIVE_ID = "sleeper_id"
KIND = "crosswalk"
PROVIDES = ["espn_id", "yahoo_id", "cbs_id", "mfl_id", "fantasypros_id", "merge_name"]
name = "dp_playerids"
ttl = timedelta(days=7)

_URL = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_playerids.csv"


def request(params: dict[str, Any]) -> RequestSpec:
    return RequestSpec(url=_URL)


def validate(raw: RawPayload) -> None:
    head = raw.body[:300].decode("utf-8", errors="replace")
    # A GitHub 404 page is HTML and sails past naive size checks.
    if head.lstrip().startswith("<") or "sleeper_id" not in head:
        raise SourceError(f"unexpected playerids CSV header: {head[:80]!r}")


def parse(raw: RawPayload) -> SourceDataset:
    reader = csv.DictReader(io.StringIO(raw.body.decode("utf-8")))
    rows = []
    for r in reader:
        if not r.get("sleeper_id") or r["sleeper_id"] == "NA":
            continue
        # DynastyProcess uses PK for kickers; Sleeper (our canon) uses K.
        position = "K" if r.get("position") == "PK" else r.get("position", "")
        rows.append(
            {
                "sleeper_id": r["sleeper_id"],
                "position": position,
                "espn_id": None if r.get("espn_id") in (None, "NA", "") else r["espn_id"],
                "yahoo_id": None if r.get("yahoo_id") in (None, "NA", "") else r["yahoo_id"],
                "cbs_id": None if r.get("cbs_id") in (None, "NA", "") else r["cbs_id"],
                "mfl_id": None if r.get("mfl_id") in (None, "NA", "") else r["mfl_id"],
                "fantasypros_id": (
                    None if r.get("fantasypros_id") in (None, "NA", "") else r["fantasypros_id"]
                ),
                "merge_name": r.get("merge_name", ""),
                "name": r.get("name", ""),
                "team": r.get("team") or None,
            }
        )
    return SourceDataset(source=name, rows=rows)
