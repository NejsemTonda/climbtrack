-- Same tables as the Supabase original (minus auth/profiles and deprecated columns).
CREATE TABLE IF NOT EXISTS groups (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  weekday INTEGER NOT NULL CHECK (weekday BETWEEN 1 AND 4),
  start_time TEXT NOT NULL,
  end_time TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS children (
  id TEXT PRIMARY KEY,
  group_id TEXT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  first_name TEXT NOT NULL,
  gender TEXT NOT NULL DEFAULT 'kluk' CHECK (gender IN ('kluk','holka')),
  birth_year INTEGER,
  climbing_years INTEGER,
  level TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_children_group ON children(group_id);

CREATE TABLE IF NOT EXISTS routes (
  id TEXT PRIMARY KEY,
  color TEXT NOT NULL DEFAULT '',
  chain_number INTEGER NOT NULL DEFAULT 0,  -- 0 for traverzy and bouldery
  created_at TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'cesta' CHECK (kind IN ('cesta','traverz','boulder')),
  points INTEGER,                           -- bouldery only
  name TEXT NOT NULL DEFAULT '',            -- traverzy only
  photo_path TEXT,                          -- bouldery only, file in PHOTO_DIR
  description TEXT
);
-- same-colour bouldery stay distinct
CREATE UNIQUE INDEX IF NOT EXISTS routes_non_boulder_identity ON routes (kind, color, chain_number, name) WHERE kind <> 'boulder';

CREATE TABLE IF NOT EXISTS climbs (
  id TEXT PRIMARY KEY,
  child_id TEXT NOT NULL REFERENCES children(id) ON DELETE CASCADE,
  group_id TEXT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  route_id TEXT REFERENCES routes(id) ON DELETE SET NULL,
  route_color TEXT,
  chain_number INTEGER,
  grade TEXT NOT NULL DEFAULT '',  -- only old records use it
  style TEXT NOT NULL,
  note TEXT,
  climbed_at TEXT NOT NULL,
  route_kind TEXT NOT NULL DEFAULT 'cesta',
  route_name TEXT,
  points INTEGER,          -- traverz/boulder points at the time of logging
  catalog_route_id TEXT    -- traverz/boulder identity, no FK so it survives route removal
);
CREATE INDEX IF NOT EXISTS idx_climbs_child ON climbs(child_id);
CREATE INDEX IF NOT EXISTS idx_climbs_group ON climbs(group_id, climbed_at);

CREATE TABLE IF NOT EXISTS lezik_challenges (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL DEFAULT '',
  starts_on TEXT NOT NULL,
  ends_on TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lezik_tasks (
  id TEXT PRIMARY KEY,
  challenge_id TEXT NOT NULL REFERENCES lezik_challenges(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  reward INTEGER NOT NULL DEFAULT 1,
  levels TEXT NOT NULL DEFAULT '[]',  -- JSON array of level names, empty = everyone
  position INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS lezik_completions (
  id TEXT PRIMARY KEY,
  child_id TEXT NOT NULL REFERENCES children(id) ON DELETE CASCADE,
  task_id TEXT REFERENCES lezik_tasks(id) ON DELETE SET NULL,
  task_title TEXT NOT NULL,
  reward INTEGER NOT NULL,
  completed_at TEXT NOT NULL,
  UNIQUE (child_id, task_id)
);


CREATE TABLE IF NOT EXISTS lezik_weekly_bonuses (
  id TEXT PRIMARY KEY,
  child_id TEXT NOT NULL REFERENCES children(id) ON DELETE CASCADE,
  week_start TEXT NOT NULL,  -- Monday, YYYY-MM-DD
  reward INTEGER NOT NULL CHECK (reward BETWEEN 1 AND 4),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (child_id, week_start)
);
