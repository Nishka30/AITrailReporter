"""category knowledge: primary Location+Category knowledge architecture

Adds the PRIMARY knowledge system's table (category_knowledge) and links it
into the two existing systems it now sits alongside:

  - place_questions gains category_assignment_id / verifying_knowledge_id /
    volatility, so it can carry category-driven questions (the EXCEPTION
    hazard system -- KnowledgeTypeConfig/Question -- is untouched).
  - observations gains category_knowledge_id and knowledge_type_id becomes
    nullable, so Observation can serve as the shared verification ledger for
    BOTH systems (exactly one of the two FKs populated per row, enforced by
    a CHECK constraint).

STRICTLY ADDITIVE for all existing data: every new column is nullable, no
existing row's knowledge_type_id is touched, and the new CHECK constraint is
satisfied trivially by every pre-existing observations row (knowledge_type_id
NOT NULL, category_knowledge_id NULL, so knowledge_type_id IS NOT NULL <>
category_knowledge_id IS NOT NULL is true <> false = true).

No historical CategoryKnowledge rows are fabricated from existing
PlaceQuestion/Observation data -- the new architecture applies prospectively
only (see the design doc's explicit instruction not to infer an unreliable
historical mapping).

Revision ID: 7d49106bf60d
Revises: 23188bdb04e9
Create Date: 2026-09-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "7d49106bf60d"
down_revision: Union[str, None] = "23188bdb04e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "category_knowledge",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_text", sa.Text(), nullable=False),
        sa.Column("volatility", sa.String(length=20), nullable=False),
        sa.Column("freshness_duration_hours", sa.Integer(), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_question_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_finding_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("superseded_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="ai_research"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["category_assignment_id"], ["location_category_assignments.id"], ondelete="RESTRICT"
        ),
        # source_question_id -> place_questions and superseded_by_id -> self
        # are added as separate ALTERs below, AFTER place_questions gets its
        # own new columns and after this table exists -- category_knowledge
        # and place_questions each reference the other (category_knowledge.
        # source_question_id -> place_questions.id, place_questions.
        # verifying_knowledge_id -> category_knowledge.id), so one of the two
        # FKs must be added after both tables/columns exist.
        sa.ForeignKeyConstraint(["source_finding_id"], ["place_research_findings.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_category_knowledge_location_id", "category_knowledge", ["location_id"])
    op.create_index(
        "ix_category_knowledge_assignment_active",
        "category_knowledge",
        ["category_assignment_id", "active"],
    )

    op.add_column(
        "place_questions",
        sa.Column("category_assignment_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "place_questions",
        sa.Column("verifying_knowledge_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "place_questions",
        sa.Column("volatility", sa.String(length=20), nullable=True),
    )
    op.create_foreign_key(
        "fk_place_questions_category_assignment_id",
        "place_questions",
        "location_category_assignments",
        ["category_assignment_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_place_questions_verifying_knowledge_id",
        "place_questions",
        "category_knowledge",
        ["verifying_knowledge_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # The two forward references deferred from create_table above.
    op.create_foreign_key(
        "fk_category_knowledge_source_question_id",
        "category_knowledge",
        "place_questions",
        ["source_question_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_category_knowledge_superseded_by_id",
        "category_knowledge",
        "category_knowledge",
        ["superseded_by_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "observations",
        sa.Column("category_knowledge_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_observations_category_knowledge_id",
        "observations",
        "category_knowledge",
        ["category_knowledge_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_observations_category_knowledge_id", "observations", ["category_knowledge_id"]
    )
    op.alter_column("observations", "knowledge_type_id", nullable=True)
    op.create_check_constraint(
        "ck_observations_exactly_one_knowledge_target",
        "observations",
        "(knowledge_type_id IS NOT NULL) <> (category_knowledge_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_observations_exactly_one_knowledge_target", "observations", type_="check"
    )
    op.alter_column("observations", "knowledge_type_id", nullable=False)
    op.drop_index("ix_observations_category_knowledge_id", table_name="observations")
    op.drop_constraint(
        "fk_observations_category_knowledge_id", "observations", type_="foreignkey"
    )
    op.drop_column("observations", "category_knowledge_id")

    op.drop_constraint(
        "fk_category_knowledge_superseded_by_id", "category_knowledge", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_category_knowledge_source_question_id", "category_knowledge", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_place_questions_verifying_knowledge_id", "place_questions", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_place_questions_category_assignment_id", "place_questions", type_="foreignkey"
    )
    op.drop_column("place_questions", "volatility")
    op.drop_column("place_questions", "verifying_knowledge_id")
    op.drop_column("place_questions", "category_assignment_id")

    op.drop_index("ix_category_knowledge_assignment_active", table_name="category_knowledge")
    op.drop_index("ix_category_knowledge_location_id", table_name="category_knowledge")
    op.drop_table("category_knowledge")
