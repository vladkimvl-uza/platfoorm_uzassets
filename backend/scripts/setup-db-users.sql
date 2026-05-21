-- =====================================================================
-- DB user separation — least-privilege roles for runtime services.
--
-- Roles:
--   uza_app     — backend runtime: DML on app tables, NO DDL, NO superuser
--   uza_backup  — backup container: SELECT-only across app tables
--
-- Original `uza` owner role is the migrations/admin role (Alembic only).
--
-- IDEMPOTENT: re-run for password rotation or to fix drift.
--
-- Required psql -v parameters:
--   :app_password    — password for uza_app
--   :backup_password — password for uza_backup
--   :app_db          — database name (e.g. uzassets)
-- =====================================================================

-- ─── uza_app: DML role for backend runtime ──────────────────────────
\set ON_ERROR_STOP off
CREATE ROLE uza_app LOGIN;
\set ON_ERROR_STOP on
ALTER ROLE uza_app WITH LOGIN PASSWORD :'app_password';

GRANT CONNECT ON DATABASE :"app_db" TO uza_app;
GRANT USAGE ON SCHEMA public TO uza_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO uza_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO uza_app;

-- Future tables created by Alembic auto-granted to app.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO uza_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO uza_app;

-- Audit chain protection: app may INSERT but NOT UPDATE/DELETE rows.
-- Tampering with chain rows is the highest-privilege op we have.
REVOKE UPDATE, DELETE ON audit_log FROM uza_app;

-- Sentinel row lock for audit chain serialization: SELECT FOR UPDATE
-- requires UPDATE privilege even though the sentinel is never actually
-- updated.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'audit_chain_lock') THEN
        GRANT SELECT, UPDATE ON audit_chain_lock TO uza_app;
        REVOKE INSERT, DELETE, TRUNCATE ON audit_chain_lock FROM uza_app;
    END IF;
END $$;


-- ─── uza_backup: SELECT-only for pg_dump ────────────────────────────
\set ON_ERROR_STOP off
CREATE ROLE uza_backup LOGIN;
\set ON_ERROR_STOP on
ALTER ROLE uza_backup WITH LOGIN PASSWORD :'backup_password';

GRANT CONNECT ON DATABASE :"app_db" TO uza_backup;
GRANT USAGE ON SCHEMA public TO uza_backup;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO uza_backup;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO uza_backup;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO uza_backup;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON SEQUENCES TO uza_backup;

-- Belt-and-suspenders: explicit revoke of write privileges
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM uza_backup;


-- ─── Audit ──────────────────────────────────────────────────────────
SELECT 'Role setup complete' AS status;
SELECT rolname, rolsuper, rolcanlogin FROM pg_roles
WHERE rolname IN ('uza', 'uza_app', 'uza_backup') ORDER BY rolname;
