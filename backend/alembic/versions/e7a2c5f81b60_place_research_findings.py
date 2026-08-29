"""Place research findings: provenance for every generated invitation.

Adds the record of WHAT was researched about a place and WHY a question was
asked, plus the locality that makes that research possible in the first place.

Nothing here is destructive and nothing is backfilled with a guess. Existing
place questions simply have no source_finding_id (they predate findings being
recorded), and existing locations have no locality until one is resolved on
their next research run.

Revision ID: e7a2c5f81b60
Revises: d5b1c8e37a94
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e7a2c5f81b60"
down_revision = "d5b1c8e37a94"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Where a place is, in words a search engine understands. Without it,
    # research for "Ganesh Temple" matches every city on earth.
    op.add_column("locations", sa.Column("locality", sa.String(length=255), nullable=True))

    op.create_table(
        "place_research_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("research_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("topic", sa.String(length=30), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source_urls", postgresql.JSONB(), nullable=True),
        sa.Column("source_titles", postgresql.JSONB(), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        # Findings die with their place -- they describe nothing without it.
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="CASCADE"),
        # But they OUTLIVE the run that scheduled them: the finding is the
        # durable evidence, the research row is just lifecycle bookkeeping.
        sa.ForeignKeyConstraint(
            ["research_id"], ["place_question_research.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_place_research_findings_location",
        "place_research_findings",
        ["location_id", "retrieved_at"],
    )

    # Which finding justified this invitation. SET NULL rather than CASCADE: a
    # question that has already been answered must never be destroyed by the
    # removal of its provenance row.
    op.add_column(
        "place_questions",
        sa.Column("source_finding_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_place_questions_source_finding",
        "place_questions",
        "place_research_findings",
        ["source_finding_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Existing questions were produced by the previous design, which searched
    # and generated in a single model call and therefore has no stored finding
    # to point at. Deactivated rather than deleted -- an already-answered
    # question must keep existing so its answer's provenance still resolves --
    # so the next request researches the place again under the new pipeline.
    op.execute("UPDATE place_questions SET active = false")
    op.execute("UPDATE place_question_research SET researched_at = NULL")


def downgrade() -> None:
    op.drop_constraint(
        "fk_place_questions_source_finding", "place_questions", type_="foreignkey"
    )
    op.drop_column("place_questions", "source_finding_id")
    op.drop_index("ix_place_research_findings_location", table_name="place_research_findings")
    op.drop_table("place_research_findings")
    op.drop_column("locations", "locality")
