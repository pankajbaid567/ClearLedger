"""fix_estimated_cost_float_to_integer

Revision ID: 9f3a8b2e5d1d
Revises: 9f3a8b2e5d1c
Create Date: 2026-09-04 12:30:00.000000

Convert estimated_cost from Float to Integer (micro-dollars)
This eliminates floating-point arithmetic and maintains consistency with
the project's "integer-only" financial principle. 1 micro-dollar = $0.000001
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f3a8b2e5d1d"
down_revision: Union[str, None] = "9f3a8b2e5d1c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new integer column for micro-dollars
    op.add_column(
        "ai_analyses",
        sa.Column("estimated_cost_microdollars", sa.BigInteger(), nullable=True),
    )
    
    # Migrate existing float data to micro-dollars (multiply by 1,000,000)
    op.execute(
        """
        UPDATE ai_analyses 
        SET estimated_cost_microdollars = CAST(ROUND(estimated_cost * 1000000) AS BIGINT)
        """
    )
    
    # Set default for new column
    op.execute(
        """
        UPDATE ai_analyses 
        SET estimated_cost_microdollars = 0
        WHERE estimated_cost_microdollars IS NULL
        """
    )
    
    # Make column non-nullable
    op.alter_column(
        "ai_analyses",
        "estimated_cost_microdollars",
        nullable=False,
    )
    
    # Drop old float column
    op.drop_column("ai_analyses", "estimated_cost")
    
    # Rename new column to estimated_cost
    op.alter_column(
        "ai_analyses",
        "estimated_cost_microdollars",
        new_column_name="estimated_cost",
    )


def downgrade() -> None:
    # Rename current integer column
    op.alter_column(
        "ai_analyses",
        "estimated_cost",
        new_column_name="estimated_cost_microdollars",
    )
    
    # Add back float column
    op.add_column(
        "ai_analyses",
        sa.Column("estimated_cost", sa.Float(), server_default="0", nullable=False),
    )
    
    # Migrate micro-dollars back to float (divide by 1,000,000)
    op.execute(
        """
        UPDATE ai_analyses 
        SET estimated_cost = CAST(estimated_cost_microdollars AS FLOAT) / 1000000.0
        """
    )
    
    # Drop micro-dollar column
    op.drop_column("ai_analyses", "estimated_cost_microdollars")
