"""Add POI discovery: provenance on locations, plus a discovery lifecycle table

Everything place-specific in this system hangs off the `locations` table. With
it empty -- which is what production had -- geographic_context resolves nothing,
place research never runs, and Explore falls back to generic prompts no matter
how good the downstream prompts are. This migration adds what is needed to fill
that table from real web research instead of by hand.

Purely additive: no drops, no data rewrites, no backfill that guesses. Existing
Locations keep source='manual', which is their true provenance -- every one of
them was created by a person or a seed, so nothing is being assumed.

Revision ID: d5b1c8e37a94
Revises: c3f7a91d4e28
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "d5b1c8e37a94"
down_revision = "c3f7a91d4e28"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- locations: provenance ------------------------------------------
    op.add_column(
        "locations",
        # 'manual' | 'discovered'. server_default rather than a backfill: every
        # pre-existing row genuinely IS manual, so the default states a fact.
        sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"),
    )
    op.add_column("locations", sa.Column("place_kind", sa.String(length=50), nullable=True))
    # Real citations backing a discovered place. A discovered row is never
    # written without at least one.
    op.add_column("locations", sa.Column("source_urls", postgresql.JSONB(), nullable=True))
    op.add_column("locations", sa.Column("discovery_cell_key", sa.String(length=32), nullable=True))
    op.create_index("ix_locations_discovery_cell_key", "locations", ["discovery_cell_key"])

    # --- poi_discovery: the run lifecycle -------------------------------
    op.create_table(
        "poi_discovery",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # UNIQUE: two guides in the same neighbourhood can never start
        # duplicate paid research runs. The constraint is the real guarantee.
        sa.Column("cell_key", sa.String(length=32), nullable=False, unique=True),
        sa.Column("center_latitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("center_longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("provider", sa.String(length=50), nullable=False, server_default="anthropic"),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("discovered_count", sa.Integer(), nullable=False, server_default="0"),
        # Only a SUCCESSFUL run moves this, so repeated failures can never look
        # like fresh coverage and suppress retries.
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_poi_discovery_status", "poi_discovery", ["status"])


def downgrade() -> None:
    op.drop_index("ix_poi_discovery_status", table_name="poi_discovery")
    op.drop_table("poi_discovery")
    op.drop_index("ix_locations_discovery_cell_key", table_name="locations")
    op.drop_column("locations", "discovery_cell_key")
    op.drop_column("locations", "source_urls")
    op.drop_column("locations", "place_kind")
    op.drop_column("locations", "source")
