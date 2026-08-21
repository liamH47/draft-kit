-- Tags are opinions about PLAYERS, not about leagues.
--
-- Keying them by league meant every new league started with an empty board:
-- you tagged your targets, started next week's draft, and they were gone.
-- Worse, the tags were still there — stranded against a league id you would
-- never open again. One set of opinions per user, carried into every league.
--
-- Existing rows are merged, newest wins per player (SQLite's documented
-- bare-column behaviour picks the row that MAX(updated_at) came from).
CREATE TABLE player_tag_user (
    user_id    TEXT NOT NULL DEFAULT 'local',
    player_id  TEXT NOT NULL,
    tag        TEXT,          -- target | at_adp | fade  (null clears)
    note       TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, player_id)
);

INSERT INTO player_tag_user (user_id, player_id, tag, note, updated_at)
SELECT user_id, player_id, tag, note, MAX(updated_at)
FROM player_tag
GROUP BY user_id, player_id;

DROP TABLE player_tag;
ALTER TABLE player_tag_user RENAME TO player_tag;
