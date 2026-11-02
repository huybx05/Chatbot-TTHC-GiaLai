BEGIN;

ALTER TABLE users DROP CONSTRAINT IF EXISTS chk_users_role;

UPDATE users
SET role = 'client'
WHERE role IN ('viewer', 'analyst');

ALTER TABLE users
    ALTER COLUMN role SET DEFAULT 'client';

ALTER TABLE users
    ADD CONSTRAINT chk_users_role CHECK (role IN ('client', 'admin'));

COMMIT;
