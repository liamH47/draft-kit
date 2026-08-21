"""What each source actually returns, versus what it claims to provide.

Run this whenever you want to know whether the data underneath the app has
moved: new fields appearing, promised fields vanishing, coverage quietly
degrading. It is the standing mechanism for noticing that a feed changed
before a draft does it for you.

    uv run python scripts/census.py            # from snapshots (offline safe)
    uv run python scripts/census.py --live     # force a fresh fetch first
"""

import argparse
import json
from collections import Counter
from typing import Any

from draftkit.config import get_settings
from draftkit.snapshots.store import SnapshotStore
from draftkit.sources import registry


def census_one(store: SnapshotStore, info, params: dict[str, Any], live: bool) -> dict[str, Any]:
    dataset, meta = store.get(info.module, params, force=live)
    rows = dataset.rows
    present: Counter = Counter()
    for row in rows:
        for key, value in row.items():
            if value not in (None, "", {}, []):
                present[key] += 1
    total = len(rows) or 1
    fill = {key: round(count / total, 3) for key, count in sorted(present.items())}

    claimed = set(info.provides)
    observed = set(fill)
    return {
        "source": info.name,
        "rows": len(rows),
        "stale": meta.stale,
        "fetched_at": meta.fetched_at.isoformat(),
        "fill_rate": fill,
        # The three things worth acting on:
        "missing": sorted(claimed - observed),  # promised but absent
        "undeclared": sorted(observed - claimed - {"name", "position", "team"}),
        "sparse": sorted(k for k, v in fill.items() if v < 0.5),
        "by_position": dict(Counter(r.get("position") for r in rows if r.get("position"))),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="force a fresh fetch")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    settings = get_settings()
    store = SnapshotStore(settings.snapshots_dir)
    season = settings.season
    jobs = [
        ("sleeper_players", {}),
        ("sleeper_projections", {"season": season}),
        ("dp_playerids", {}),
        ("ffcalc", {"format": "half_ppr", "teams": 12, "year": season}),
        ("borischen", {"format": "half_ppr"}),
        ("espn_market", {"season": season}),
        ("espn_projections", {"season": season}),
        ("cbs_rankings", {"format": "ppr"}),
        ("yahoo_adp", {"start": 0}),
    ]

    reports, problems = [], 0
    for source_name, params in jobs:
        info = registry.by_name(source_name)
        try:
            report = census_one(store, info, params, args.live)
        except Exception as exc:
            reports.append({"source": source_name, "error": str(exc)})
            problems += 1
            continue
        reports.append(report)
        problems += bool(report["missing"])

    if args.json:
        print(json.dumps(reports, indent=2))
        return 1 if problems else 0

    for r in reports:
        if "error" in r:
            print(f"\n{r['source']}\n  UNAVAILABLE: {r['error']}")
            continue
        flag = " (stale)" if r["stale"] else ""
        print(f"\n{r['source']}: {r['rows']} rows{flag}")
        if r["by_position"]:
            counts = ", ".join(f"{k}={v}" for k, v in sorted(r["by_position"].items()))
            print("  positions:", counts)
        if r["missing"]:
            print("  MISSING (declared but never populated):", ", ".join(r["missing"]))
        if r["undeclared"]:
            print("  new fields not declared in PROVIDES:", ", ".join(r["undeclared"]))
        if r["sparse"]:
            print("  sparse (<50% filled):", ", ".join(r["sparse"]))
    print("\nrun with --live before a draft to check against fresh payloads")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
