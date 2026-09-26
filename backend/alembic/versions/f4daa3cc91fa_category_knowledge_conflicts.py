"""category knowledge conflicts

Part 2 of the knowledge-architecture hardening pass: an explicit resolution
queue for a re-verification whose relationship to already-verified
CategoryKnowledge could not be confidently classified as CONFIRMS or
CONTRADICTS (see app/services/knowledge_relation.py). Additive only -- no
existing table, column or constraint is touched.

Revision ID: f4daa3cc91fa
Revises: 7d49106bf60d
Create Date: 2026-09-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f4daa3cc91fa"
down_revision: Union[str, None] = "7d49106bf60d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "category_knowledge_conflicts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("category_knowledge_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("new_answer_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("resolution", sa.String(length=20), nullable=True),
        sa.Column("resolved_knowledge_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_by", sa.String(length=100), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_knowledge_id"], ["category_knowledge.id"],
            name="fk_category_knowledge_conflicts_category_knowledge_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["observation_id"], ["observations.id"],
            name="fk_category_knowledge_conflicts_observation_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_knowledge_id"], ["category_knowledge.id"],
            name="fk_category_knowledge_conflicts_resolved_knowledge_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_category_knowledge_conflicts_status",
        "category_knowledge_conflicts",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_category_knowledge_conflicts_status", table_name="category_knowledge_conflicts")
    op.drop_table("category_knowledge_conflicts")
