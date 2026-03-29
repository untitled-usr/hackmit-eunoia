DO $$
DECLARE
  username_unique_constraint TEXT;
BEGIN
  SELECT tc.constraint_name
  INTO username_unique_constraint
  FROM information_schema.table_constraints tc
  JOIN information_schema.constraint_column_usage ccu
    ON tc.constraint_name = ccu.constraint_name
  WHERE tc.table_schema = 'public'
    AND tc.table_name = 'user'
    AND tc.constraint_type = 'UNIQUE'
    AND ccu.column_name = 'username'
  LIMIT 1;

  IF username_unique_constraint IS NOT NULL THEN
    EXECUTE format('ALTER TABLE "user" DROP CONSTRAINT %I', username_unique_constraint);
  END IF;
END $$;

ALTER TABLE "user"
  ALTER COLUMN username SET DEFAULT '',
  ALTER COLUMN avatar_url SET DEFAULT '';

UPDATE "user"
SET avatar_url = '';

UPDATE "user"
SET
  username = '',
  nickname = ''
WHERE role = 'USER';
