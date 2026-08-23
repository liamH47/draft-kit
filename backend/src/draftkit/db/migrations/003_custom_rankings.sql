-- Ranking lists the user brings in themselves.
--
-- The published lists we pull (ESPN, CBS, Boris Chen) are the ones that are
-- free to fetch; the good ones a user pays for are not, and scraping them is
-- not on. So the user pastes them: a PDF cheat sheet, a spreadsheet column,
-- a table selected off a page. Whatever the shape, it arrives as text and
-- lands here.
--
-- Rows keep the name exactly as pasted alongside the player id we resolved it
-- to. Unresolved rows are STORED, with a null player_id, rather than dropped:
-- a silently shorter list is how you find out in round four that your cheat
-- sheet lost fourteen players.
CREATE TABLE custom_ranking (
    user_id     TEXT NOT NULL DEFAULT 'local',
    list_name   TEXT NOT NULL,
    rank        INTEGER NOT NULL,
    player_id   TEXT,           -- null when the pasted name never resolved
    source_name TEXT NOT NULL,  -- what the paste actually said
    position    TEXT,
    team        TEXT,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (user_id, list_name, rank)
);

CREATE INDEX custom_ranking_by_player ON custom_ranking (user_id, player_id);
