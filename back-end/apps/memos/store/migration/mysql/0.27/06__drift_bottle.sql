CREATE TABLE `drift_bottle` (
  `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `uid` VARCHAR(64) NOT NULL UNIQUE,
  `memo_id` INT NOT NULL UNIQUE,
  `creator_id` INT NOT NULL,
  `status` VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
  `created_ts` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_ts` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE `drift_candidate_pool` (
  `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `user_id` INT NOT NULL,
  `source_memo_id` INT NOT NULL,
  `candidate_memo_id` INT NOT NULL,
  `score` DOUBLE NOT NULL DEFAULT 0,
  `tier` INT NOT NULL DEFAULT 0,
  `refreshed_ts` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `expires_ts` BIGINT NOT NULL DEFAULT 0,
  UNIQUE(`user_id`, `source_memo_id`, `candidate_memo_id`)
);

CREATE TABLE `drift_pick_log` (
  `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `user_id` INT NOT NULL,
  `memo_id` INT NOT NULL,
  `candidate_pool_id` INT DEFAULT NULL,
  `picked_ts` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(`user_id`, `memo_id`)
);

CREATE TABLE `drift_daily_quota` (
  `user_id` INT NOT NULL,
  `day` VARCHAR(16) NOT NULL,
  `picked_count` INT NOT NULL DEFAULT 0,
  `limit_count` INT NOT NULL DEFAULT 5,
  `updated_ts` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(`user_id`, `day`)
);

CREATE INDEX `idx_drift_bottle_creator_status` ON `drift_bottle`(`creator_id`, `status`);
CREATE INDEX `idx_drift_candidate_user_expires` ON `drift_candidate_pool`(`user_id`, `expires_ts`);
CREATE INDEX `idx_drift_pick_user_time` ON `drift_pick_log`(`user_id`, `picked_ts`);
