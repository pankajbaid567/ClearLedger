-- Run once as the schema owner after migrations. Application login roles should
-- be members of clearledger_runtime and must not own this schema or its tables.
\set ON_ERROR_STOP on

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'clearledger_runtime') THEN
        CREATE ROLE clearledger_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
END $$;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM clearledger_runtime;
GRANT USAGE ON SCHEMA public TO clearledger_runtime;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO clearledger_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO clearledger_runtime;
REVOKE ALL ON TABLE alembic_version FROM clearledger_runtime;

GRANT UPDATE ON TABLE
    reconciliation_runs,
    source_files,
    reconciliation_cases,
    candidate_relationships,
    evidence_edges,
    invariant_results,
    exceptions,
    ai_analyses,
    follow_up_tasks,
    cash_position_snapshots,
    idempotency_records
TO clearledger_runtime;
GRANT DELETE ON TABLE idempotency_records TO clearledger_runtime;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT ON TABLES TO clearledger_runtime;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO clearledger_runtime;
