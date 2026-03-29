-- system_setting
CREATE TABLE `system_setting` (
  `name` VARCHAR(256) NOT NULL PRIMARY KEY,
  `value` LONGTEXT NOT NULL,
  `description` TEXT NOT NULL
);

-- user
CREATE TABLE `user` (
  `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `created_ts` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_ts` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `row_status` VARCHAR(256) NOT NULL DEFAULT 'NORMAL',
  `username` VARCHAR(256) NOT NULL DEFAULT '',
  `role` VARCHAR(256) NOT NULL DEFAULT 'USER',
  `nickname` VARCHAR(256) NOT NULL DEFAULT '',
  `password_hash` VARCHAR(256) NOT NULL,
  `avatar_url` LONGTEXT NOT NULL,
  `description` VARCHAR(256) NOT NULL DEFAULT '',
  `gender` VARCHAR(64) NOT NULL DEFAULT '',
  `age` INT NOT NULL DEFAULT 0
);

-- user_setting
CREATE TABLE `user_setting` (
  `user_id` INT NOT NULL,
  `key` VARCHAR(256) NOT NULL,
  `value` LONGTEXT NOT NULL,
  UNIQUE(`user_id`,`key`)
);

-- memo
CREATE TABLE `memo` (
  `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `uid` VARCHAR(256) NOT NULL UNIQUE,
  `creator_id` INT NOT NULL,
  `created_ts` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_ts` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `row_status` VARCHAR(256) NOT NULL DEFAULT 'NORMAL',
  `content` TEXT NOT NULL,
  `visibility` VARCHAR(256) NOT NULL DEFAULT 'PRIVATE',
  `pinned` BOOLEAN NOT NULL DEFAULT FALSE,
  `payload` JSON NOT NULL
);

-- memo_relation
CREATE TABLE `memo_relation` (
  `memo_id` INT NOT NULL,
  `related_memo_id` INT NOT NULL,
  `type` VARCHAR(256) NOT NULL,
  UNIQUE(`memo_id`,`related_memo_id`,`type`)
);

-- attachment
CREATE TABLE `attachment` (
  `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `uid` VARCHAR(256) NOT NULL UNIQUE,
  `creator_id` INT NOT NULL,
  `created_ts` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_ts` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `filename` TEXT NOT NULL,
  `blob` MEDIUMBLOB,
  `type` VARCHAR(256) NOT NULL DEFAULT '',
  `size` INT NOT NULL DEFAULT '0',
  `memo_id` INT DEFAULT NULL,
  `storage_type` VARCHAR(256) NOT NULL DEFAULT '',
  `reference` TEXT NOT NULL DEFAULT (''),
  `payload` TEXT NOT NULL
);

-- activity
CREATE TABLE `activity` (
  `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `creator_id` INT NOT NULL,
  `created_ts` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `type` VARCHAR(256) NOT NULL DEFAULT '',
  `level` VARCHAR(256) NOT NULL DEFAULT 'INFO',
  `payload` TEXT NOT NULL
);

-- idp
CREATE TABLE `idp` (
  `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `uid` VARCHAR(256) NOT NULL UNIQUE,
  `name` TEXT NOT NULL,
  `type` TEXT NOT NULL,
  `identifier_filter` VARCHAR(256) NOT NULL DEFAULT '',
  `config` TEXT NOT NULL
);

-- inbox
CREATE TABLE `inbox` (
  `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `created_ts` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `sender_id` INT NOT NULL,
  `receiver_id` INT NOT NULL,
  `status` TEXT NOT NULL,
  `message` TEXT NOT NULL
);

-- reaction
CREATE TABLE `reaction` (
  `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `created_ts` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `creator_id` INT NOT NULL,
  `content_id` VARCHAR(256) NOT NULL,
  `reaction_type` VARCHAR(256) NOT NULL,
  UNIQUE(`creator_id`,`content_id`,`reaction_type`)  
);

-- drift_bottle
CREATE TABLE `drift_bottle` (
  `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `uid` VARCHAR(64) NOT NULL UNIQUE,
  `memo_id` INT NOT NULL UNIQUE,
  `creator_id` INT NOT NULL,
  `status` VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
  `created_ts` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_ts` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- drift_candidate_pool
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

-- drift_pick_log
CREATE TABLE `drift_pick_log` (
  `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `user_id` INT NOT NULL,
  `memo_id` INT NOT NULL,
  `candidate_pool_id` INT DEFAULT NULL,
  `picked_ts` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(`user_id`, `memo_id`)
);

-- drift_daily_quota
CREATE TABLE `drift_daily_quota` (
  `user_id` INT NOT NULL,
  `day` VARCHAR(16) NOT NULL,
  `picked_count` INT NOT NULL DEFAULT 0,
  `limit_count` INT NOT NULL DEFAULT 5,
  `updated_ts` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(`user_id`, `day`)
);

-- drift_bottle_tag
CREATE TABLE `drift_bottle_tag` (
  `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `drift_bottle_id` INT NOT NULL,
  `tag` VARCHAR(64) NOT NULL,
  `normalized_tag` VARCHAR(64) NOT NULL,
  `created_ts` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(`drift_bottle_id`, `normalized_tag`)
);

CREATE INDEX `idx_drift_bottle_creator_status` ON `drift_bottle`(`creator_id`, `status`);
CREATE INDEX `idx_drift_candidate_user_expires` ON `drift_candidate_pool`(`user_id`, `expires_ts`);
CREATE INDEX `idx_drift_pick_user_time` ON `drift_pick_log`(`user_id`, `picked_ts`);
CREATE INDEX `idx_drift_bottle_tag_normalized` ON `drift_bottle_tag`(`normalized_tag`);
CREATE INDEX `idx_drift_bottle_tag_bottle` ON `drift_bottle_tag`(`drift_bottle_id`);

-- purge legacy PAT records
DELETE FROM `user_setting`
WHERE `key` = 'PERSONAL_ACCESS_TOKENS';
