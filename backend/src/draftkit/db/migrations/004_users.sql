-- Accounts: one row per Google identity that has ever signed in. Display and
-- audit only — authorization lives in the DRAFTKIT_ALLOWED_EMAILS list, so
-- removing an email locks someone out without touching this table.
CREATE TABLE user_account (
    google_sub  TEXT PRIMARY KEY,
    email       TEXT NOT NULL,
    name        TEXT,
    picture     TEXT,
    first_login TEXT NOT NULL,
    last_login  TEXT NOT NULL
);

-- The per-user lookups every request now makes.
CREATE INDEX league_by_user ON league (user_id);
CREATE INDEX draft_session_by_user ON draft_session (user_id);
