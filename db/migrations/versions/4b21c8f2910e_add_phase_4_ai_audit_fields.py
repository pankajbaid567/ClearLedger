"""add phase 4 AI audit fields

Revision ID: 4b21c8f2910e
Revises: 849be651d3d6
Create Date: 2026-08-31 20:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "4b21c8f2910e"
down_revision: Union[str, Sequence[str], None] = "849be651d3d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "candidate_relationships",
        sa.Column("actor_type", sa.Text(), server_default="SYSTEM", nullable=False),
    )
    op.add_column("ai_analyses", sa.Column("provider", sa.Text(), nullable=True))
    op.add_column(
        "ai_analyses",
        sa.Column("status", sa.Text(), server_default="UNKNOWN", nullable=False),
    )
    op.add_column(
        "ai_analyses",
        sa.Column("estimated_cost", sa.Float(), server_default="0", nullable=False),
    )
    op.add_column(
        "ai_analyses",
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "ai_analyses",
        sa.Column("deterministic_checks", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("ai_analyses", sa.Column("error_type", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_analyses", "error_type")
    op.drop_column("ai_analyses", "deterministic_checks")
    op.drop_column("ai_analyses", "attempts")
    op.drop_column("ai_analyses", "estimated_cost")
    op.drop_column("ai_analyses", "status")
    op.drop_column("ai_analyses", "provider")
    op.drop_column("candidate_relationships", "actor_type")
