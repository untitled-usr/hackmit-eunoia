CREATE TABLE `drift_bottle_tag` (
  `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `drift_bottle_id` INT NOT NULL,
  `tag` VARCHAR(64) NOT NULL,
  `normalized_tag` VARCHAR(64) NOT NULL,
  `created_ts` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(`drift_bottle_id`, `normalized_tag`)
);

CREATE INDEX `idx_drift_bottle_tag_normalized` ON `drift_bottle_tag`(`normalized_tag`);
CREATE INDEX `idx_drift_bottle_tag_bottle` ON `drift_bottle_tag`(`drift_bottle_id`);
