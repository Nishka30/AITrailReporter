"""Curated seed places/questions (Thamel/Lukla launch data) and hub eligibility

Adds what's needed to layer human-curated place data on top of the existing
Location/PlaceQuestion system, additively:

  - locations.coordinate_confidence / coordinate_type -- provenance the
    curator supplied about how much to trust a seed row's own coordinate.
    Null for every non-seed row (see location.py's own comments).
  - place_questions.source -- 'ai_research' (true history, server_default
    for every existing row) or 'seed'. This is the ONLY thing that changes
    meaning for existing data, and it changes nothing observable: every row
    that exists today really was produced by the Perplexity+Claude pipeline.
  - curated_hubs -- a small, separate table marking a Location as a curated
    seed-question hub with its own eligibility radius (see
    db/models/curated_hub.py for why this is its own table rather than
    columns on `locations`). Empty after this migration; populated by
    services/seed_import.py, not by migration data.

Nothing here is destructive: no drops, no data rewrites beyond the one
provenance backfill described above, and 'seed' is additive to `provider`'s
existing free-text value space (it was already nullable free text, so no
column change is needed there at all).

Revision ID: 7c1e4a9b3d20
Revises: 481faa86f41c
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "7c1e4a9b3d20"
down_revision = "481faa86f41c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- locations: seed-coordinate provenance -----------------------------
    op.add_column("locations", sa.Column("coordinate_confidence", sa.String(length=20), nullable=True))
    op.add_column("locations", sa.Column("coordinate_type", sa.String(length=50), nullable=True))

    # --- place_questions: distinguish curated from AI-researched -----------
    # server_default (not a backfilling UPDATE) because it states a plain
    # fact about every row that already exists: it really was produced by
    # the research pipeline, since seed rows did not exist before this
    # migration.
    op.add_column(
        "place_questions",
        sa.Column("source", sa.String(length=20), nullable=False, server_default="ai_research"),
    )

    # --- curated_hubs: which Locations are curated seed-question hubs ------
    op.create_table(
        "curated_hubs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "location_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("locations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("radius_meters", sa.Integer(), nullable=False, server_default="2000"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_unique_constraint("uq_curated_hubs_location_id", "curated_hubs", ["location_id"])


def downgrade() -> None:
    op.drop_table("curated_hubs")
    op.drop_column("place_questions", "source")
    op.drop_column("locations", "coordinate_type")
    op.drop_column("locations", "coordinate_confidence")
