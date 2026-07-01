CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL DEFAULT '',
  role TEXT NOT NULL DEFAULT 'viewer',    -- owner|viewer
  status TEXT NOT NULL DEFAULT 'invited',  -- invited|active|disabled
  theme TEXT NOT NULL DEFAULT 'auto',       -- auto|light|dark
  created_at TEXT NOT NULL,
  last_seen_at TEXT
);
CREATE TABLE IF NOT EXISTS activity (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL, ts TEXT NOT NULL,
  action TEXT NOT NULL, target TEXT DEFAULT '', meta TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_activity_user_ts ON activity(user_id, ts);
CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL, ts TEXT NOT NULL, action TEXT NOT NULL,
  item_id TEXT, date TEXT, title TEXT, tags TEXT, text TEXT
);
CREATE INDEX IF NOT EXISTS idx_feedback_user ON feedback(user_id, ts);
CREATE TABLE IF NOT EXISTS favorites (
  user_id INTEGER NOT NULL, item_id TEXT NOT NULL,
  date TEXT, title TEXT, ts TEXT, PRIMARY KEY(user_id, item_id)
);
CREATE TABLE IF NOT EXISTS follows (
  user_id INTEGER NOT NULL, item_id TEXT NOT NULL,
  title TEXT, topics TEXT, entities TEXT, ts TEXT, PRIMARY KEY(user_id, item_id)
);
CREATE TABLE IF NOT EXISTS reads (
  user_id INTEGER NOT NULL, item_id TEXT NOT NULL, ts TEXT, PRIMARY KEY(user_id, item_id)
);
CREATE TABLE IF NOT EXISTS requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL, ts TEXT, text TEXT, tags TEXT, status TEXT DEFAULT 'new'
);
