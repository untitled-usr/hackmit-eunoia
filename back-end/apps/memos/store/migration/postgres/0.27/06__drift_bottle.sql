CREATE TABLE drift_bottle (
  id SERIAL PRIMARY KEY,
  uid TEXT NOT NULL UNIQUE,
  memo_id INTEGER NOT NULL UNIQUE,
  creator_id INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  created_ts BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW()),
  updated_ts BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW())
);

CREATE TABLE drift_candidate_pool (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL,
  source_memo_id INTEGER NOT NULL,
  candidate_memo_id INTEGER NOT NULL,
  score DOUBLE PRECISION NOT NULL DEFAULT 0,
  tier INTEGER NOT NULL DEFAULT 0,
  refreshed_ts BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW()),
  expires_ts BIGINT NOT NULL DEFAULT 0,
  UNIQUE(user_id, source_memo_id, candidate_memo_id)
);

CREATE TABLE drift_pick_log (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL,
  memo_id INTEGER NOT NULL,
  candidate_pool_id INTEGER,
  picked_ts BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW()),
  UNIQUE(user_id, memo_id)
);

CREATE TABLE drift_daily_quota (
  user_id INTEGER NOT NULL,
  day TEXT NOT NULL,
  picked_count INTEGER NOT NULL DEFAULT 0,
  limit_count INTEGER NOT NULL DEFAULT 5,
  updated_ts BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW()),
  PRIMARY KEY(user_id, day)
);

CREATE INDEX idx_drift_bottle_creator_status ON drift_bottle(creator_id, status);
CREATE INDEX idx_drift_candidate_user_expires ON drift_candidate_pool(user_id, expires_ts);
CREATE INDEX idx_drift_pick_user_time ON drift_pick_log(user_id, picked_ts);
