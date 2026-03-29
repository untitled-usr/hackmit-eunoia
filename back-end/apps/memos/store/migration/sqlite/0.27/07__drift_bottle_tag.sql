CREATE TABLE drift_bottle_tag (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  drift_bottle_id INTEGER NOT NULL,
  tag TEXT NOT NULL,
  normalized_tag TEXT NOT NULL,
  created_ts BIGINT NOT NULL DEFAULT (strftime('%s', 'now')),
  UNIQUE(drift_bottle_id, normalized_tag)
);

CREATE INDEX idx_drift_bottle_tag_normalized ON drift_bottle_tag(normalized_tag);
CREATE INDEX idx_drift_bottle_tag_bottle ON drift_bottle_tag(drift_bottle_id);
