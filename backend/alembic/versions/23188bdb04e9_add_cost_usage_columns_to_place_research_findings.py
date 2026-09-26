"""add cost/usage columns to place_research_findings

Adds input_tokens/output_tokens/cost_usd to place_research_findings, populated
going forward from the research provider's own reported usage (see
app/services/research/perplexity_provider.py). Strictly additive and nullable
-- existing rows simply have no usage data, which is the honest state for
calls made before this column existed, not a zero cost.

Revision ID: 23188bdb04e9
Revises: f1a2b3c4d5e6
Create Date: 2026-09-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "23188bdb04e9"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "place_research_findings", sa.Column("input_tokens", sa.Integer(), nullable=True)
    )
    op.add_column(
        "place_research_findings", sa.Column("output_tokens", sa.Integer(), nullable=True)
    )
    op.add_column(
        "place_research_findings", sa.Column("cost_usd", sa.Numeric(10, 6), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("place_research_findings", "cost_usd")
    op.drop_column("place_research_findings", "output_tokens")
    op.drop_column("place_research_findings", "input_tokens")
