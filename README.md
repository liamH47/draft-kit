# draftkit

A free fantasy football draft assistant: an interactive cheat sheet that tracks your
draft as it happens and recommends picks based on value vs ADP, positional scarcity,
tier breaks, and your own player tags — built on free, no-auth data sources.

## Status

Early scaffold (M0). See `docs/` (coming) and the milestone list below.

- **M0** — scaffold: FastAPI backend, Vite/React frontend, CI, Docker ✅
- **M1** — data spine: source adapters (Sleeper, FantasyFootballCalculator, Boris Chen
  tiers, dynastyprocess ID crosswalk), snapshot cache with stale fallback, scored player
  pool per league config ✅
- **M2** — draft core: league setup, draft sessions, manual pick entry + undo,
  target/fade tags and notes, crash-safe resume ✅
- **M3** — MVP: keyboard-first draft board, VORP/tiers/ADP-delta, recommendations with
  reasons — usable in a live draft ✅
- **M4** — live Sleeper sync + availability/VONA/run detection
- **M5** — hosted mode for friends
- **M6+** — Yahoo OAuth sync, ESPN browser extension

## Dev

Backend needs [uv](https://docs.astral.sh/uv/); frontend needs Node 22+.

```sh
make dev        # backend :8000 + frontend :5173 (Vite proxies /api)
make check      # lint + tests, both halves
make serve      # production shape: one process serving built UI + API
make docker     # build the container
make e2e        # browser smoke test against a running server
```

Before your first draft, pull live data for the season:

```sh
cd backend && uv run python scripts/warm_snapshots.py
```

`/api/health` reports how old each source's snapshot is — worth a glance on draft
morning. If a source is unreachable the app keeps serving the last good snapshot and
shows a banner rather than going blank.

## Using it on draft night

1. **Set up the league** — teams, scoring, your draft slot.
2. **Prep the cheat sheet** — tag players **T** (target: take ahead of ADP), **A** (at
   ADP) or **F** (fade: only well past ADP). Tags feed straight into the recommendations.
3. **Draft** — the quick-entry box stays focused: type a few letters, **Enter** marks a
   player taken by someone else, **Shift+Enter** marks him as your pick. `/` refocuses
   the box, and undo fixes a mis-click.

Configuration is env-only; see `.env.example`. All runtime data (SQLite, source
snapshots) lives under `DRAFTKIT_DATA_DIR` (default `./data`).

## Data sources & credits

ADP data from [Fantasy Football Calculator](https://fantasyfootballcalculator.com).
Player data and projections from the public [Sleeper](https://sleeper.com) API.
Tier data by [Boris Chen](http://www.borischen.co/).
Player ID crosswalk from [DynastyProcess](https://github.com/dynastyprocess/data).
