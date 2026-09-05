\set ON_ERROR_STOP on

DO $$
DECLARE
    attrs record;
BEGIN
    SELECT rolsuper, rolcreatedb, rolcreaterole INTO attrs
    FROM pg_roles WHERE rolname = 'clearledger_runtime';
    IF NOT FOUND OR attrs.rolsuper OR attrs.rolcreatedb OR attrs.rolcreaterole THEN
        RAISE EXCEPTION 'clearledger_runtime has unsafe role attributes';
    END IF;
    IF has_schema_privilege('clearledger_runtime', 'public', 'CREATE') THEN
        RAISE EXCEPTION 'clearledger_runtime can create schema objects';
    END IF;
    IF has_table_privilege('clearledger_runtime', 'audit_events', 'UPDATE')
       OR has_table_privilege('clearledger_runtime', 'audit_events', 'DELETE')
       OR has_table_privilege('clearledger_runtime', 'raw_source_rows', 'UPDATE')
       OR has_table_privilege('clearledger_runtime', 'raw_source_rows', 'DELETE')
       OR has_table_privilege('clearledger_runtime', 'human_decisions', 'UPDATE')
       OR has_table_privilege('clearledger_runtime', 'policy_versions', 'UPDATE') THEN
        RAISE EXCEPTION 'clearledger_runtime can mutate append-only evidence';
    END IF;
    IF has_table_privilege('clearledger_runtime', 'alembic_version', 'SELECT')
       OR has_table_privilege('clearledger_runtime', 'alembic_version', 'INSERT') THEN
        RAISE EXCEPTION 'clearledger_runtime can access migration state';
    END IF;
    IF NOT has_table_privilege('clearledger_runtime', 'reconciliation_runs', 'UPDATE')
       OR NOT has_table_privilege('clearledger_runtime', 'idempotency_records', 'DELETE') THEN
        RAISE EXCEPTION 'clearledger_runtime lacks required projection/claim privileges';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_class AS relation
        JOIN pg_roles AS owner ON owner.oid = relation.relowner
        JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = 'public'
          AND owner.rolname = 'clearledger_runtime'
    ) THEN
        RAISE EXCEPTION 'clearledger_runtime owns public relations';
    END IF;
END $$;
