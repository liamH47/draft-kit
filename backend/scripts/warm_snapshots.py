"""Force-fetch every source into the snapshot store.

Run this the morning of a draft (and before recording new test fixtures):
    cd backend && uv run python scripts/warm_snapshots.py
"""

from draftkit.config import get_settings
from draftkit.snapshots.store import SnapshotStore
from draftkit.sources import (
    borischen_tiers,
    dp_playerids,
    espn_market,
    ffcalc_adp,
    sleeper_players,
    sleeper_projections,
)


def main() -> int:
    settings = get_settings()
    store = SnapshotStore(settings.snapshots_dir)
    season = settings.season
    jobs = [
        (sleeper_players, {}),
        (sleeper_projections, {"season": season}),
        (dp_playerids, {}),
        (espn_market, {"season": season}),
    ]
    for preset in ("standard", "half_ppr", "ppr"):
        jobs.append((ffcalc_adp, {"format": preset, "teams": 12, "year": season}))
        jobs.append((borischen_tiers, {"format": preset}))

    failures = 0
    for adapter, params in jobs:
        try:
            dataset, meta = store.get(adapter, params, force=True)
            note = " (served from an older snapshot)" if meta.stale else ""
            print(f"ok    {adapter.name:22} {len(dataset.rows):>6} rows{note}  {params}")
            failures += 1 if meta.stale else 0
        except Exception as exc:
            print(f"FAIL  {adapter.name:22} {params}")
            print(f"      {exc}")
            failures += 1

    if failures:
        print(
            "\nA failed source costs its columns, not the draft — the board still "
            "builds from whatever succeeded.\nRun `python scripts/census.py` to see "
            "what each source that did work actually returned."
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
