"""Force-fetch every source into the snapshot store.

Run this the morning of a draft (and before recording new test fixtures):
    cd backend && uv run python scripts/warm_snapshots.py
"""

from draftkit.config import get_settings
from draftkit.snapshots.store import SnapshotStore
from draftkit.sources import (
    borischen_tiers,
    dp_playerids,
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
    ]
    for preset in ("standard", "half_ppr", "ppr"):
        jobs.append((ffcalc_adp, {"format": preset, "teams": 12, "year": season}))
        jobs.append((borischen_tiers, {"format": preset}))

    failures = 0
    for adapter, params in jobs:
        try:
            _, meta = store.get(adapter, params, force=True)
            print(f"ok    {adapter.name} {params} (stale={meta.stale})")
            failures += 1 if meta.stale else 0
        except Exception as exc:
            print(f"FAIL  {adapter.name} {params}: {exc}")
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
