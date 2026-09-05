"""Pool-safe claims, execution leases, and migration provenance.

Revision ID: d9c7e21a4f10
Revises: b5f41aa832d0
"""

import sqlalchemy as sa
from alembic import op

revision = "d9c7e21a4f10"
down_revision = "b5f41aa832d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "idempotency_records",
        sa.Column("state", sa.Text(), nullable=False, server_default="COMPLETED"),
    )
    op.add_column("idempotency_records", sa.Column("claim_token", sa.Text(), nullable=True))
    op.add_column(
        "idempotency_records",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_idempotency_state",
        "idempotency_records",
        "state IN ('IN_PROGRESS', 'COMPLETED')",
    )
    op.create_index(
        "ix_idempotency_lease",
        "idempotency_records",
        ["state", "lease_expires_at"],
    )

    op.add_column(
        "reconciliation_runs", sa.Column("execution_attempt_token", sa.Text(), nullable=True)
    )
    op.add_column(
        "reconciliation_runs",
        sa.Column("execution_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_reconciliation_runs_parent_run_id", "reconciliation_runs", ["parent_run_id"]
    )

    # The previous migration added revision columns conservatively. Establish the
    # actual historical sequence before accepting optimistic review writes.
    op.execute("DROP TRIGGER IF EXISTS human_decisions_append_only ON human_decisions")
    op.execute(
        """WITH ranked AS (
            SELECT id, reconciliation_run_id,
                   row_number() OVER (
                       PARTITION BY reconciliation_run_id ORDER BY created_at, id
                   ) AS revision
            FROM human_decisions
        )
        UPDATE human_decisions AS decision
        SET review_revision=ranked.revision,
            execution_revision=run.execution_revision
        FROM ranked
        JOIN reconciliation_runs AS run ON run.id=ranked.reconciliation_run_id
        WHERE decision.id=ranked.id"""
    )
    op.execute(
        """UPDATE reconciliation_runs AS run
        SET review_revision=COALESCE((
            SELECT max(decision.review_revision)
            FROM human_decisions AS decision
            WHERE decision.reconciliation_run_id=run.id
        ), 0)"""
    )
    op.execute(
        """CREATE TRIGGER human_decisions_append_only
        BEFORE UPDATE OR DELETE ON human_decisions FOR EACH ROW
        EXECUTE FUNCTION clearledger_reject_evidence_mutation()"""
    )

    # Reconstruct every available historical source hash. Incomplete legacy runs
    # are labelled rather than presented as fully attested executions.
    op.execute(
        """WITH manifests AS (
            SELECT run.id,
                   count(source.id) AS source_count,
                   COALESCE(
                       jsonb_object_agg(
                           source.source_type || '.csv', source.file_checksum
                           ORDER BY source.source_type
                       ) FILTER (WHERE source.id IS NOT NULL),
                       '{}'::jsonb
                   ) AS file_checksums
            FROM reconciliation_runs AS run
            LEFT JOIN source_files AS source ON source.reconciliation_run_id=run.id
            GROUP BY run.id
        )
        UPDATE reconciliation_runs AS run
        SET input_manifest=jsonb_build_object(
            'dataset_id', COALESCE(
                run.config->>'dataset_id',
                'legacy_' || left(COALESCE(run.dataset_checksum, 'unknown'), 12)
            ),
            'file_checksums', manifests.file_checksums,
            'provenance_status', CASE
                WHEN manifests.source_count=5 AND run.dataset_checksum IS NOT NULL
                THEN 'reconstructed'
                ELSE 'legacy_incomplete'
            END
        )
        FROM manifests
        WHERE run.id=manifests.id AND run.input_manifest='{}'::jsonb"""
    )

    # The old case-only task key can be ambiguous after multiple executions. Abort
    # instead of silently choosing a run. An operator can assign the explicit run ID
    # shown by the query in docs/AUTHENTICATION.md, then rerun this migration.
    op.execute(
        """DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM follow_up_tasks WHERE reconciliation_run_id IS NULL) THEN
            RAISE EXCEPTION USING
                MESSAGE='Unscoped legacy follow_up_tasks require explicit run mapping',
                HINT='Set follow_up_tasks.reconciliation_run_id after reviewing matching '
                     'reconciliation_cases, then rerun the migration.';
        END IF;
        END $$"""
    )
    op.alter_column("follow_up_tasks", "reconciliation_run_id", nullable=False)

    op.execute(
        """CREATE FUNCTION clearledger_protect_completed_run_baseline()
        RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
        IF OLD.status='COMPLETED' AND (
            NEW.owner_subject IS DISTINCT FROM OLD.owner_subject OR
            NEW.parent_run_id IS DISTINCT FROM OLD.parent_run_id OR
            NEW.execution_revision IS DISTINCT FROM OLD.execution_revision OR
            NEW.as_of_at IS DISTINCT FROM OLD.as_of_at OR
            NEW.policy_version_id IS DISTINCT FROM OLD.policy_version_id OR
            NEW.policy_snapshot IS DISTINCT FROM OLD.policy_snapshot OR
            NEW.input_manifest IS DISTINCT FROM OLD.input_manifest OR
            NEW.dataset_checksum IS DISTINCT FROM OLD.dataset_checksum OR
            NEW.result_checksum IS DISTINCT FROM OLD.result_checksum OR
            NEW.rule_set_version IS DISTINCT FROM OLD.rule_set_version OR
            NEW.app_version IS DISTINCT FROM OLD.app_version OR
            NEW.config IS DISTINCT FROM OLD.config OR
            NEW.total_source_rows IS DISTINCT FROM OLD.total_source_rows OR
            NEW.total_cases IS DISTINCT FROM OLD.total_cases OR
            NEW.status IS DISTINCT FROM OLD.status
        ) THEN
            RAISE EXCEPTION 'Completed execution baseline is immutable'
            USING ERRCODE='55000';
        END IF;
        RETURN NEW;
        END $$"""
    )
    op.execute(
        """CREATE TRIGGER reconciliation_runs_baseline_immutable
        BEFORE UPDATE ON reconciliation_runs FOR EACH ROW
        EXECUTE FUNCTION clearledger_protect_completed_run_baseline()"""
    )
    op.execute(
        """CREATE FUNCTION clearledger_protect_source_file()
        RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE run_status text; BEGIN
        SELECT status INTO run_status FROM reconciliation_runs
        WHERE id=OLD.reconciliation_run_id;
        IF run_status IN ('COMPLETED', 'FAILED') THEN
            RAISE EXCEPTION 'Frozen execution source files are immutable'
            USING ERRCODE='55000';
        END IF;
        RETURN OLD;
        END $$"""
    )
    op.execute(
        """CREATE TRIGGER source_files_frozen
        BEFORE UPDATE OR DELETE ON source_files FOR EACH ROW
        EXECUTE FUNCTION clearledger_protect_source_file()"""
    )
    op.execute(
        """CREATE FUNCTION clearledger_protect_case_evidence()
        RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE run_status text; BEGIN
        SELECT status INTO run_status FROM reconciliation_runs
        WHERE id=OLD.reconciliation_run_id;
        IF run_status='COMPLETED' AND (
            NEW.case_id IS DISTINCT FROM OLD.case_id OR
            NEW.reconciliation_run_id IS DISTINCT FROM OLD.reconciliation_run_id OR
            NEW.source_entity_ids IS DISTINCT FROM OLD.source_entity_ids OR
            NEW.record_snapshot IS DISTINCT FROM OLD.record_snapshot OR
            NEW.gross_amount_paise IS DISTINCT FROM OLD.gross_amount_paise OR
            NEW.currency IS DISTINCT FROM OLD.currency
        ) THEN
            RAISE EXCEPTION 'Completed case evidence is immutable'
            USING ERRCODE='55000';
        END IF;
        RETURN NEW;
        END $$"""
    )
    op.execute(
        """CREATE TRIGGER reconciliation_cases_evidence_immutable
        BEFORE UPDATE ON reconciliation_cases FOR EACH ROW
        EXECUTE FUNCTION clearledger_protect_case_evidence()"""
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS reconciliation_cases_evidence_immutable "
        "ON reconciliation_cases"
    )
    op.execute("DROP FUNCTION IF EXISTS clearledger_protect_case_evidence()")
    op.execute("DROP TRIGGER IF EXISTS source_files_frozen ON source_files")
    op.execute("DROP FUNCTION IF EXISTS clearledger_protect_source_file()")
    op.execute(
        "DROP TRIGGER IF EXISTS reconciliation_runs_baseline_immutable ON reconciliation_runs"
    )
    op.execute("DROP FUNCTION IF EXISTS clearledger_protect_completed_run_baseline()")
    op.alter_column("follow_up_tasks", "reconciliation_run_id", nullable=True)
    op.drop_constraint(
        "uq_reconciliation_runs_parent_run_id", "reconciliation_runs", type_="unique"
    )
    op.drop_column("reconciliation_runs", "execution_lease_expires_at")
    op.drop_column("reconciliation_runs", "execution_attempt_token")
    op.drop_index("ix_idempotency_lease", table_name="idempotency_records")
    op.drop_constraint("ck_idempotency_state", "idempotency_records", type_="check")
    op.drop_column("idempotency_records", "lease_expires_at")
    op.drop_column("idempotency_records", "claim_token")
    op.drop_column("idempotency_records", "state")
