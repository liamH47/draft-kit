-- draftkit initial schema.
--
-- Two things here are deliberate and load-bearing:
--  1. Every user-owned table carries user_id (default 'local'). Hosting later
--     becomes middleware that sets it — no migration.
--  2. `pick` is an append-only event log. Undo writes a tombstone rather than
--     deleting, so a live-sync source disagreeing with a manual entry stays
--     visible instead of silently overwriting history.

CREATE TABLE league (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      TEXT    NOT NULL DEFAULT 'local',
    name         TEXT    NOT NULL,
    platform     TEXT    NOT NULL DEFAULT 'other',
    num_teams    INTEGER NOT NULL,
    my_slot      INTEGER NOT NULL,
    rounds       INTEGER NOT NULL DEFAULT 15,
    scoring_preset TEXT  NOT NULL DEFAULT 'half_ppr',
    config_json  TEXT    NOT NULL,          -- full LeagueConfig (scoring overrides, roster)
    created_at   TEXT    NOT NULL
);

CREATE TABLE draft_session (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT    NOT NULL DEFAULT 'local',
    league_id   INTEGER NOT NULL REFERENCES league(id) ON DELETE CASCADE,
    name        TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'active',   -- active | complete
    sync_source TEXT,                                -- null = manual entry only
    sync_ref    TEXT,                                -- e.g. a Sleeper draft id
    created_at  TEXT    NOT NULL
);

CREATE TABLE pick (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES draft_session(id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,       -- append order, including tombstones
    overall_no  INTEGER NOT NULL,       -- 1-based overall pick number
    round_no    INTEGER NOT NULL,
    slot        INTEGER NOT NULL,
    player_id   TEXT    NOT NULL,       -- canonical (Sleeper) player id
    is_mine     INTEGER NOT NULL DEFAULT 0,
    source      TEXT    NOT NULL DEFAULT 'manual',   -- manual | sleeper | extension
    undone      INTEGER NOT NULL DEFAULT 0,          -- tombstone flag
    created_at  TEXT    NOT NULL
);
CREATE UNIQUE INDEX pick_session_seq ON pick(session_id, seq);
CREATE INDEX pick_session_live ON pick(session_id, undone, overall_no);

CREATE TABLE player_tag (
    user_id    TEXT NOT NULL DEFAULT 'local',
    league_id  INTEGER NOT NULL REFERENCES league(id) ON DELETE CASCADE,
    player_id  TEXT NOT NULL,
    tag        TEXT,          -- target | at_adp | fade  (null clears)
    note       TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, league_id, player_id)
);
