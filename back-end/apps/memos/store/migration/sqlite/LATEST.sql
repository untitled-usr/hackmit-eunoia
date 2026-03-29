-- system_setting
CREATE TABLE system_setting (
  name TEXT NOT NULL,
  value TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  UNIQUE(name)
);

-- user
CREATE TABLE user (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_ts BIGINT NOT NULL DEFAULT (strftime('%s', 'now')),
  updated_ts BIGINT NOT NULL DEFAULT (strftime('%s', 'now')),
  row_status TEXT NOT NULL CHECK (row_status IN ('NORMAL', 'ARCHIVED')) DEFAULT 'NORMAL',
  username TEXT NOT NULL DEFAULT '',
  role TEXT NOT NULL DEFAULT 'USER',
  nickname TEXT NOT NULL DEFAULT '',
  password_hash TEXT NOT NULL,
  avatar_url TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  gender TEXT NOT NULL DEFAULT '',
  age INTEGER NOT NULL DEFAULT 0
);

-- user_setting
CREATE TABLE user_setting (
  user_id INTEGER NOT NULL,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  UNIQUE(user_id, key)
);

-- memo
CREATE TABLE memo (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  uid TEXT NOT NULL UNIQUE,
  creator_id INTEGER NOT NULL,
  created_ts BIGINT NOT NULL DEFAULT (strftime('%s', 'now')),
  updated_ts BIGINT NOT NULL DEFAULT (strftime('%s', 'now')),
  row_status TEXT NOT NULL CHECK (row_status IN ('NORMAL', 'ARCHIVED')) DEFAULT 'NORMAL',
  content TEXT NOT NULL DEFAULT '',
  visibility TEXT NOT NULL CHECK (visibility IN ('PUBLIC', 'PRIVATE')) DEFAULT 'PRIVATE',
  pinned INTEGER NOT NULL CHECK (pinned IN (0, 1)) DEFAULT 0,
  payload TEXT NOT NULL DEFAULT '{}'
);

-- memo_relation
CREATE TABLE memo_relation (
  memo_id INTEGER NOT NULL,
  related_memo_id INTEGER NOT NULL,
  type TEXT NOT NULL,
  UNIQUE(memo_id, related_memo_id, type)
);

-- attachment
CREATE TABLE attachment (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  uid TEXT NOT NULL UNIQUE,
  creator_id INTEGER NOT NULL,
  created_ts BIGINT NOT NULL DEFAULT (strftime('%s', 'now')),
  updated_ts BIGINT NOT NULL DEFAULT (strftime('%s', 'now')),
  filename TEXT NOT NULL DEFAULT '',
  blob BLOB DEFAULT NULL,
  type TEXT NOT NULL DEFAULT '',
  size INTEGER NOT NULL DEFAULT 0,
  memo_id INTEGER,
  storage_type TEXT NOT NULL DEFAULT '',
  reference TEXT NOT NULL DEFAULT '',
  payload TEXT NOT NULL DEFAULT '{}'
);

-- activity
CREATE TABLE activity (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  creator_id INTEGER NOT NULL,
  created_ts BIGINT NOT NULL DEFAULT (strftime('%s', 'now')),
  type TEXT NOT NULL DEFAULT '',
  level TEXT NOT NULL CHECK (level IN ('INFO', 'WARN', 'ERROR')) DEFAULT 'INFO',
  payload TEXT NOT NULL DEFAULT '{}'
);

-- idp
CREATE TABLE idp (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  uid TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  identifier_filter TEXT NOT NULL DEFAULT '',
  config TEXT NOT NULL DEFAULT '{}'
);

-- inbox
CREATE TABLE inbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_ts BIGINT NOT NULL DEFAULT (strftime('%s', 'now')),
  sender_id INTEGER NOT NULL,
  receiver_id INTEGER NOT NULL,
  status TEXT NOT NULL,
  message TEXT NOT NULL DEFAULT '{}'
);

-- reaction
CREATE TABLE reaction (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_ts BIGINT NOT NULL DEFAULT (strftime('%s', 'now')),
  creator_id INTEGER NOT NULL,
  content_id TEXT NOT NULL,
  reaction_type TEXT NOT NULL,
  UNIQUE(creator_id, content_id, reaction_type)
);

-- drift_bottle
CREATE TABLE drift_bottle (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  uid TEXT NOT NULL UNIQUE,
  memo_id INTEGER NOT NULL UNIQUE,
  creator_id INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  created_ts BIGINT NOT NULL DEFAULT (strftime('%s', 'now')),
  updated_ts BIGINT NOT NULL DEFAULT (strftime('%s', 'now'))
);

-- drift_candidate_pool
CREATE TABLE drift_candidate_pool (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  source_memo_id INTEGER NOT NULL,
  candidate_memo_id INTEGER NOT NULL,
  score REAL NOT NULL DEFAULT 0,
  tier INTEGER NOT NULL DEFAULT 0,
  refreshed_ts BIGINT NOT NULL DEFAULT (strftime('%s', 'now')),
  expires_ts BIGINT NOT NULL DEFAULT 0,
  UNIQUE(user_id, source_memo_id, candidate_memo_id)
);

-- drift_pick_log
CREATE TABLE drift_pick_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  memo_id INTEGER NOT NULL,
  candidate_pool_id INTEGER,
  picked_ts BIGINT NOT NULL DEFAULT (strftime('%s', 'now')),
  UNIQUE(user_id, memo_id)
);

-- drift_daily_quota
CREATE TABLE drift_daily_quota (
  user_id INTEGER NOT NULL,
  day TEXT NOT NULL,
  picked_count INTEGER NOT NULL DEFAULT 0,
  limit_count INTEGER NOT NULL DEFAULT 5,
  updated_ts BIGINT NOT NULL DEFAULT (strftime('%s', 'now')),
  PRIMARY KEY(user_id, day)
);

-- drift_bottle_tag
CREATE TABLE drift_bottle_tag (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  drift_bottle_id INTEGER NOT NULL,
  tag TEXT NOT NULL,
  normalized_tag TEXT NOT NULL,
  created_ts BIGINT NOT NULL DEFAULT (strftime('%s', 'now')),
  UNIQUE(drift_bottle_id, normalized_tag)
);

CREATE INDEX idx_drift_bottle_creator_status ON drift_bottle(creator_id, status);
CREATE INDEX idx_drift_candidate_user_expires ON drift_candidate_pool(user_id, expires_ts);
CREATE INDEX idx_drift_pick_user_time ON drift_pick_log(user_id, picked_ts);
CREATE INDEX idx_drift_bottle_tag_normalized ON drift_bottle_tag(normalized_tag);
CREATE INDEX idx_drift_bottle_tag_bottle ON drift_bottle_tag(drift_bottle_id);

-- purge legacy PAT records
DELETE FROM user_setting
WHERE key = 'PERSONAL_ACCESS_TOKENS';
