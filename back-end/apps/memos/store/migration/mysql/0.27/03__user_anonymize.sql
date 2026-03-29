SET @unique_index_name := (
  SELECT INDEX_NAME
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'user'
    AND NON_UNIQUE = 0
    AND COLUMN_NAME = 'username'
  LIMIT 1
);

SET @drop_index_sql := IF(
  @unique_index_name IS NULL,
  'SELECT 1',
  CONCAT('ALTER TABLE `user` DROP INDEX `', @unique_index_name, '`')
);

PREPARE drop_stmt FROM @drop_index_sql;
EXECUTE drop_stmt;
DEALLOCATE PREPARE drop_stmt;

ALTER TABLE `user`
  MODIFY `username` VARCHAR(256) NOT NULL DEFAULT '';

UPDATE `user`
SET `avatar_url` = '';

UPDATE `user`
SET
  `username` = '',
  `nickname` = ''
WHERE `role` = 'USER';
