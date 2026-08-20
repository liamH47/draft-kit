# Working in this repo

draftkit is a free fantasy football draft assistant: a Python/FastAPI + SQLite backend
and a Vite/React/TypeScript frontend, run locally during a live draft.

## Specialist agents

Long-lived specialists live in `.claude/agents/` and are meant to be reused for the life
of the project, not spun up ad hoc:

- `draft-strategy-analyst` — quality of the advice: value model, baselines, tiers, ADP
- `draft-night-ux` — using it under a pick clock: entry speed, error recovery, density
- `draft-reliability` — what breaks mid-draft; the sceptic about new features
- `draft-data-sync` — source adapters, joins, and platform sync
- `league-format-specialist` — roster shape, flex/superflex, league size, autodrafters

**When new specialist expertise is needed, save it here rather than defining it inline.**
An agent definition accumulates project knowledge in its prompt, gets versioned with the
code, and is available to everyone who clones the repo. Give each one a mandate narrow
enough that it disagrees with the others — a panel that always agrees is one agent.

For decisions of consequence, run several of them and make them argue rather than report
in parallel. Their disagreements are the useful part; a proposal that survives a hostile
review from a rival specialist is worth more than four that were never contested.

## Testing

Backend coverage is gated at **100%** in `pyproject.toml` — `make check` fails below it.
That is not perfectionism: an uncovered line in this codebase is a branch that will first
execute during somebody's live draft, and most of the interesting ones are error paths.
When a line is genuinely untestable, make it testable (extract the constant, inject the
dependency) rather than lowering the gate.

The frontend is covered by TypeScript strictness plus the Playwright run in `e2e/`.
Blanket component-test coverage there would cost more than it catches; the E2E asserts
the flows that matter.

## The one rule that matters

A draft happens once and cannot be re-run. Anything that could make the board wrong,
slow, or blank during those ninety minutes outranks any feature. Prefer degrading
visibly over degrading silently.

## Orientation

- `make dev` — backend on :8000, frontend on :5173 (Vite proxies `/api`)
- `make check` — lint, types and tests, both halves
- `make e2e` — browser smoke test against a running server
- `cd backend && uv run python scripts/warm_snapshots.py` — pull live source data
- Engine code (`backend/src/draftkit/engine/`) is pure functions with no I/O. Keep it
  that way; it is why the math is testable.
- Every pick producer — manual entry, a poller, a future browser extension — goes through
  `draft/ingest.py::record_pick`. Never add a second path.

## Data sources

Sleeper, FantasyFootballCalculator, Boris Chen tiers, and the DynastyProcess ID
crosswalk — all free and no-auth. FantasyPros data is off-limits on ToS grounds; credit
FFC and Boris Chen visibly.
