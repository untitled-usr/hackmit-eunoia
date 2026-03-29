-- Migrate deprecated PROTECTED visibility to PUBLIC.
UPDATE `memo`
SET `visibility` = 'PUBLIC'
WHERE `visibility` = 'PROTECTED';

-- Normalize legacy user preference values.
UPDATE `user_setting`
SET `value` = REPLACE(`value`, '"memoVisibility":"PROTECTED"', '"memoVisibility":"PUBLIC"')
WHERE `key` = 'GENERAL'
  AND `value` LIKE '%"memoVisibility":"PROTECTED"%';
