"""Versioned executions, durable progress, ownership and append-only evidence.

Revision ID: b5f41aa832d0
Revises: 9f3a8b2e5d1d
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b5f41aa832d0"
down_revision = "9f3a8b2e5d1d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Earlier persistence multiplied domain 0..100 scores as if they were 0..1.
    op.execute(
        "UPDATE candidate_relationships SET match_score=match_score/100 WHERE match_score>10000"
    )
    op.create_check_constraint(
        "ck_candidate_match_score_range",
        "candidate_relationships",
        "match_score BETWEEN 0 AND 10000",
    )
    op.add_column("reconciliation_runs", sa.Column("owner_subject", sa.Text(), nullable=True))
    op.create_index(
        "ix_reconciliation_runs_owner_subject", "reconciliation_runs", ["owner_subject"]
    )
    op.add_column(
        "reconciliation_runs",
        sa.Column(
            "parent_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reconciliation_runs.id"),
            nullable=True,
        ),
    )
    for name, default in (
        ("execution_revision", "1"),
        ("review_revision", "0"),
        ("progress_percent", "0"),
        ("processed_records", "0"),
    ):
        op.add_column(
            "reconciliation_runs",
            sa.Column(name, sa.Integer(), nullable=False, server_default=default),
        )
    op.add_column(
        "reconciliation_runs",
        sa.Column(
            "as_of_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )
    op.add_column(
        "reconciliation_runs",
        sa.Column("stage", sa.Text(), nullable=False, server_default="created"),
    )
    for name in ("policy_snapshot", "input_manifest"):
        op.add_column(
            "reconciliation_runs",
            sa.Column(
                name, postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
            ),
        )
    op.execute(
        "UPDATE reconciliation_runs r SET policy_snapshot=p.policy_data "
        "FROM policy_versions p WHERE r.policy_version_id=p.id"
    )
    op.execute(
        "UPDATE reconciliation_runs SET stage='completed', progress_percent=100, "
        "processed_records=COALESCE(total_source_rows,0) WHERE status='COMPLETED'"
    )
    # Existing unowned demo runs are deliberately not assigned to an authenticated
    # account; a deployment migration must explicitly map owners.
    for name, default in (("execution_revision", "1"), ("review_revision", "0")):
        op.add_column(
            "human_decisions", sa.Column(name, sa.Integer(), nullable=False, server_default=default)
        )
    op.add_column(
        "follow_up_tasks",
        sa.Column(
            "reconciliation_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reconciliation_runs.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_follow_up_tasks_reconciliation_run_id", "follow_up_tasks", ["reconciliation_run_id"]
    )
    op.execute("""UPDATE follow_up_tasks t SET reconciliation_run_id=c.run_id FROM
        (SELECT case_id, (array_agg(reconciliation_run_id))[1] AS run_id FROM reconciliation_cases
         GROUP BY case_id HAVING count(*)=1) c WHERE t.case_id=c.case_id""")
    op.execute("""CREATE FUNCTION clearledger_reject_evidence_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
        RAISE EXCEPTION 'ClearLedger evidence is append-only: %', TG_TABLE_NAME
        USING ERRCODE='55000'; END $$""")
    for table in ("raw_source_rows", "audit_events", "policy_versions", "human_decisions"):
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION clearledger_reject_evidence_mutation()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION clearledger_reject_evidence_mutation()"
        )


def downgrade() -> None:
    op.drop_constraint("ck_candidate_match_score_range", "candidate_relationships", type_="check")
    for table in ("raw_source_rows", "audit_events", "policy_versions", "human_decisions"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON {table}")
    op.execute("DROP FUNCTION IF EXISTS clearledger_reject_evidence_mutation()")
    op.drop_index("ix_follow_up_tasks_reconciliation_run_id", table_name="follow_up_tasks")
    op.drop_column("follow_up_tasks", "reconciliation_run_id")
    for name in ("review_revision", "execution_revision"):
        op.drop_column("human_decisions", name)
    op.drop_index("ix_reconciliation_runs_owner_subject", table_name="reconciliation_runs")
    for name in (
        "input_manifest",
        "policy_snapshot",
        "stage",
        "as_of_at",
        "processed_records",
        "progress_percent",
        "review_revision",
        "execution_revision",
        "parent_run_id",
        "owner_subject",
    ):
        op.drop_column("reconciliation_runs", name)
