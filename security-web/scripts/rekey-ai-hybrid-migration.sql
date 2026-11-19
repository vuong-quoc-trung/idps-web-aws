-- Operator-only, after backup and with all migrators stopped. AI-branch DBs only.
-- Transaction changes a single SQLx history key. Normal sqlx then applies 14..17.
BEGIN;
LOCK TABLE _sqlx_migrations IN ACCESS EXCLUSIVE MODE;
DO $$
BEGIN
    IF EXISTS (SELECT FROM _sqlx_migrations WHERE version > 14)
       OR NOT EXISTS (SELECT FROM _sqlx_migrations WHERE version = 14 AND success
           AND checksum = decode('478ba8bcc9760775c23dabc0ebbfe9872f6cfe991171aba8545255e6edb21f25d5c54d22ccb094fcdaf07786c51d972a', 'hex'))
       OR to_regclass('hybrid_incidents') IS NULL
       OR to_regclass('hybrid_proposals') IS NULL
       OR to_regclass('hybrid_decision_audit') IS NULL THEN
        RAISE EXCEPTION 'Expected original AI hybrid migration through version 14';
    END IF;
    UPDATE _sqlx_migrations SET version = 18 WHERE version = 14;
END $$;
COMMIT;
