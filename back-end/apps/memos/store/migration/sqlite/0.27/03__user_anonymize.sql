DROP TABLE IF EXISTS _user_old;

ALTER TABLE user RENAME TO _user_old;

CREATE TABLE user (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_ts BIGINT NOT NULL DEFAULT (strftime('%s', 'now')),
  updated_ts BIGINT NOT NULL DEFAULT (strftime('%s', 'now')),
  row_status TEXT NOT NULL CHECK (row_status IN ('NORMAL', 'ARCHIVED')) DEFAULT 'NORMAL',
  username TEXT NOT NULL DEFAULT '',
  role TEXT NOT NULL DEFAULT 'USER',
  email TEXT NOT NULL DEFAULT '',
  nickname TEXT NOT NULL DEFAULT '',
  password_hash TEXT NOT NULL,
  avatar_url TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  gender TEXT NOT NULL DEFAULT '',
  age INTEGER NOT NULL DEFAULT 0
);

INSERT INTO
  user (
    id,
    created_ts,
    updated_ts,
    row_status,
    username,
    role,
    email,
    nickname,
    password_hash,
    avatar_url,
    description,
    gender,
    age
  )
SELECT
  id,
  created_ts,
  updated_ts,
  row_status,
  username,
  role,
  email,
  nickname,
  password_hash,
  avatar_url,
  description,
  gender,
  age
FROM
  _user_old;

DROP TABLE IF EXISTS _user_old;

CREATE INDEX IF NOT EXISTS idx_user_username ON user (username);

UPDATE user
SET avatar_url = '';

UPDATE user
SET
  username = '',
  nickname = ''
WHERE role = 'USER';
