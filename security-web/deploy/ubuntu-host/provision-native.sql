-- Run with psql -X against the maintenance DB only, after operator approval.
-- Failure deliberately leaves partial objects for inspection; never drop or adopt them.
\set ON_ERROR_STOP on
SELECT pg_advisory_lock(708003, 17);
DO $$
BEGIN
    IF current_database() <> 'postgres' OR current_user <> 'pbl4'
       OR current_setting('server_version_num')::int / 10000 <> 17 THEN
        RAISE EXCEPTION 'Unexpected provisioning connection';
    END IF;
    IF EXISTS (SELECT FROM pg_roles WHERE rolname IN ('ws_native_security','ws_native_student'))
       OR EXISTS (SELECT FROM pg_database WHERE datname IN ('ws_native_security','ws_native_student')) THEN
        RAISE EXCEPTION 'Existing native role or DB: stop for operator review';
    END IF;
END $$;
BEGIN;
CREATE ROLE ws_native_security LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE ws_native_student LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
COMMIT;
CREATE DATABASE ws_native_security OWNER ws_native_security TEMPLATE template0 ALLOW_CONNECTIONS false;
CREATE DATABASE ws_native_student OWNER ws_native_student TEMPLATE template0 ALLOW_CONNECTIONS false;
BEGIN;
REVOKE ALL ON DATABASE ws_native_security FROM PUBLIC;
REVOKE ALL ON DATABASE ws_native_student FROM PUBLIC;
ALTER DATABASE ws_native_security ALLOW_CONNECTIONS true;
ALTER DATABASE ws_native_student ALLOW_CONNECTIONS true;
COMMIT;
