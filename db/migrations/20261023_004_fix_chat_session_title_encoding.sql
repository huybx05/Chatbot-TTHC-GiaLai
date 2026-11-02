-- The previous migration may be read as Windows-1252 by psql on Windows.
-- Keep this migration ASCII-only so its Vietnamese text is encoding-independent.

ALTER TABLE chat_sessions
    ALTER COLUMN title SET DEFAULT U&'Cu\1ED9c tr\00F2 chuy\1EC7n m\1EDBi';

UPDATE chat_sessions
SET
    title = U&'Cu\1ED9c tr\00F2 chuy\1EC7n m\1EDBi',
    updated_at = NOW()
WHERE title = convert_from(
    decode('4375c3a1c2bbe284a263207472c383c2b22063687579c3a1c2bbe280a16e206dc3a1c2bbe280ba69', 'hex'),
    'UTF8'
);
