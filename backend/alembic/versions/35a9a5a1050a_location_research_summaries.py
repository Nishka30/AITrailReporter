"""location research summaries

Adds `location_research_summaries`, a reusable, structured, WEB-RESEARCHED
summary of a Location (description, highlights, things_to_do, practical_info,
warnings, source citations) for the future Travelers website. One row per
Location (unique on location_id), upserted in place on each regeneration --
unlike `place_research_findings`, which is append-only, only the CURRENT
summary is ever useful to a reader.

This is a SEPARATE table from `category_knowledge` on purpose: the trust
boundary between "web/AI-researched content" and "TrailMind-verified
knowledge" is structural here, not just a convention a query could forget.
Nothing outside app/services/place_summary_service.py ever writes to this
table.

Revision ID: 35a9a5a1050a
Revises: 036f23e86de6
Create Date: 2026-09-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '35a9a5a1050a'
down_revision: Union[str, None] = '036f23e86de6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "location_research_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("known_for", sa.Text(), nullable=True),
        sa.Column("highlights", postgresql.JSONB(), nullable=True),
        sa.Column("things_to_do", postgresql.JSONB(), nullable=True),
        sa.Column("important_facts", postgresql.JSONB(), nullable=True),
        sa.Column("practical_info", sa.Text(), nullable=True),
        sa.Column("warnings", postgresql.JSONB(), nullable=True),
        sa.Column("source_urls", postgresql.JSONB(), nullable=True),
        sa.Column("source_titles", postgresql.JSONB(), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column("researched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["location_id"], ["locations.id"], ondelete="CASCADE"
        ),
    )


def downgrade() -> None:
    op.drop_table("location_research_summaries")
