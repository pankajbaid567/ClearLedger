"""fix_match_score_float_to_integer

Revision ID: 9f3a8b2e5d1c
Revises: 4b21c8f2910e
Create Date: 2026-09-04 12:00:00.000000

Convert match_score from Float to Integer (scaled 0-10000 for 0.0000-1.0000)
This eliminates floating-point arithmetic and maintains consistency with
the project's "integer-only" financial principle.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f3a8b2e5d1c"
down_revision: Union[str, None] = "4b21c8f2910e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new integer column
    op.add_column(
        "candidate_relationships",
        sa.Column("match_score_scaled", sa.Integer(), nullable=True),
    )
    
    # Migrate existing float data to scaled integer (multiply by 10000)
    op.execute(
        """
        UPDATE candidate_relationships 
        SET match_score_scaled = CAST(ROUND(match_score * 10000) AS INTEGER)
        WHERE match_score IS NOT NULL
        """
    )
    
    # Drop old float column
    op.drop_column("candidate_relationships", "match_score")
    
    # Rename new column to match_score
    op.alter_column(
        "candidate_relationships",
        "match_score_scaled",
        new_column_name="match_score",
    )


def downgrade() -> None:
    # Rename current integer column
    op.alter_column(
        "candidate_relationships",
        "match_score",
        new_column_name="match_score_scaled",
    )
    
    # Add back float column
    op.add_column(
        "candidate_relationships",
        sa.Column("match_score", sa.Float(), nullable=True),
    )
    
    # Migrate scaled integer back to float (divide by 10000)
    op.execute(
        """
        UPDATE candidate_relationships 
        SET match_score = CAST(match_score_scaled AS FLOAT) / 10000.0
        WHERE match_score_scaled IS NOT NULL
        """
    )
    
    # Drop scaled integer column
    op.drop_column("candidate_relationships", "match_score_scaled")
