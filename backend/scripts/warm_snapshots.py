"""Force-fetch every source into the snapshot store.

Run this the morning of a draft (and before recording new test fixtures):
    cd backend && uv run python scripts/warm_snapshots.py
"""

from draftkit.config import get_settings
from draftkit.db import repo
from draftkit.db.connection import connect
from draftkit.snapshots.store import SnapshotStore
from draftkit.sources import (
    borischen_tiers,
    cbs_rankings,
    dp_playerids,
    espn_market,
    espn_projections,
    fantasypros,
    ffcalc_adp,
    mfl_adp,
    sleeper_players,
    sleeper_projections,
    sleeper_trending,
    yahoo_adp,
)


def league_team_counts() -> set[int]:
    """FFC snapshots are keyed by team count, so warm one per configured
    league — a draft run with DRAFTKIT_OFFLINE=1 can only read what was
    warmed, and an 8-team league cannot use the 12-team file."""
    counts = {12}
    settings = get_settings()
    try:
        conn = connect(settings.db_path)
        counts |= repo.league_team_counts(conn)
        conn.close()
    except Exception:
        pass  # no database yet — the default still gets warmed
    return counts


def main() -> int:
    settings = get_settings()
    store = SnapshotStore(settings.snapshots_dir)
    season = settings.season
    jobs = [
        (sleeper_players, {}),
        (sleeper_projections, {"season": season}),
        (dp_playerids, {}),
        (espn_market, {"season": season}),
        (espn_projections, {"season": season}),
        (cbs_rankings, {"format": "ppr"}),
        (cbs_rankings, {"format": "standard"}),
        (sleeper_trending, {"kind": "add"}),
        (sleeper_trending, {"kind": "drop"}),
    ]
    # Yahoo pages are 25 wide and ADP fades around the top ~275; warm the
    # full walk so an offline draft can read every page the pool will ask for.
    for start in range(0, 400, yahoo_adp.PAGE_SIZE):
        jobs.append((yahoo_adp, {"start": start}))
    for preset in ("standard", "half_ppr", "ppr"):
        for teams in sorted(league_team_counts()):
            jobs.append((ffcalc_adp, {"format": preset, "teams": teams, "year": season}))
        jobs.append((borischen_tiers, {"format": preset}))
        jobs.append((fantasypros, {"format": preset}))
        jobs.append((mfl_adp, {"format": preset, "year": season}))

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
