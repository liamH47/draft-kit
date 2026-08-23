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

## Running it

On Windows, double-click **`start-draftkit.cmd`**. It builds the interface, starts the
app on <http://localhost:8000> and opens it. Leave that window open while you use it;
closing it stops the server.

On draft morning use **`start-draftkit-draftday.cmd`** instead. It refreshes every
source first and then pins the app to what is on disk, so no board refresh can sit
waiting on a slow feed while you are on the clock.

Everything you enter — leagues, picks, and the players you tag — is stored on your own
machine in `backend/data`, and stays there between runs. None of it lives in the
browser, so clearing cookies or site data loses nothing. Tags are additionally mirrored
to `backend/data/tags.json`, which you can read, edit, or copy to another machine; the
cheat sheet has save and load buttons for the same file, and `POST /api/tags/restore`
rebuilds the tags from it if the database is ever lost.

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

1. **Set up the league.** If it is on ESPN, paste the league ID from the URL and hit
   Import — the app reads the real roster slots and scoring, so replacement level is
   right without anyone retyping settings. A 3-WR league values receivers very
   differently from a 2-WR one, and that difference is larger than most of the
   recommendation model. Otherwise fill in the form by hand.

   Private ESPN leagues need `DRAFTKIT_ESPN_S2` and `DRAFTKIT_ESPN_SWID` in your
   `.env` (see `.env.example`). Those are credentials — they belong in that file and
   nowhere else.
2. **Prep the cheat sheet** — tag players **T** (target: take ahead of ADP), **A** (at
   ADP) or **F** (fade: only well past ADP). Tags feed straight into the recommendations.
3. **Draft** — the quick-entry box stays focused and never leaves your hands:

   | key | does |
   | --- | --- |
   | `Enter` | mark the highlighted player taken by someone else |
   | `Shift+Enter` | mark him as your pick |
   | `Ctrl+T` / `Ctrl+A` / `Ctrl+F` | tag him target / at-ADP / fade |
   | `/` | jump back to the box from anywhere |
   | `↑` `↓` | move through matches |

   Type someone already taken and the app offers to **fix that pick** instead of
   coming back empty — so mistyping pick 43 and noticing at 51 costs one correction
   rather than nine undos. A search matching nobody says so, because a blank dropdown
   is indistinguishable from a typo when you are behind the room.

Kickers and defenses are held out of the recommendations until the last three rounds —
a kicker in round 6 costs a starter, and K1 through K12 barely differ. Three things
lift the hold: reaching the window, having every other starting slot filled, or a
genuine outlier at the position. Both the positions and the window size are per-league
settings (`late_round_positions`, `late_round_window`).

Configuration is env-only; see `.env.example`. All runtime data (SQLite, source
snapshots) lives under `DRAFTKIT_DATA_DIR` (default `./data`).

## Data sources & credits

Every source is listed in **[docs/data-sources.md](docs/data-sources.md)**, which is
generated from the adapters themselves so it cannot drift. `make docs` refreshes it and
`make census` reports what each source actually returned versus what it claims to
provide — run that before a draft to catch a feed that changed shape.

ADP data from [Fantasy Football Calculator](https://fantasyfootballcalculator.com).
Player data, projections and trending adds/drops from the public
[Sleeper](https://sleeper.com) API.
ADP and draft ranks from [ESPN Fantasy](https://fantasy.espn.com/).
ADP and draft analysis from [Yahoo Fantasy Sports](https://football.fantasysports.yahoo.com/).
Rankings from [CBS Sports Fantasy](https://www.cbssports.com/fantasy/football/).
ADP data from [MyFantasyLeague](https://www.myfantasyleague.com/).
Tier data by [Boris Chen](http://www.borischen.co/).
Player ID crosswalk from [DynastyProcess](https://github.com/dynastyprocess/data).

### Bringing your own rankings

Anything we cannot fetch — a subscription list, a PDF cheat sheet, a spreadsheet
somebody emailed you — can be pasted into the app from the cheat sheet page. It is
parsed leniently (numbers, positions, teams and byes are all optional; page numbers and
header rows are discarded), resolved against the player universe, and joins the
published lists in the consensus rank. Names it could not match are reported rather
than dropped, because a list that quietly arrives short is the failure you discover in
round four.

### Rankings vs ADP

The app keeps two different things apart on purpose. **ADP** is where players actually
go — a market price. A **ranking list** is where a platform or a panel of experts says
they should go. Autodrafters walk a list mechanically and plenty of humans anchor to
whichever one is in front of them, so the gap between the two predicts a specific room.
It is deliberately the smallest term in the recommendation score: it forecasts behaviour,
not value, and the projections already answer the value question.
