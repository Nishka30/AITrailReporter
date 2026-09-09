"""Google Places provider fields on locations/submissions, replacing OSM.

Adds the provenance TrailMind needs to identify WHICH place-identification
backend supplied a Location, WHICH exact place it is (a provider place id),
and TrailMind's OWN category/subcategory derived from that provider's typing
-- see app/services/places/. Also adds Submission.external_place_id so a
guide's manually-searched-and-selected place carries its provider place id
through offline-first sync into extraction.

Nothing here is destructive or backfills a guess: existing discovered rows
(all sourced from the retired OpenStreetMap pipeline) are backfilled to
`provider='openstreetmap'` because that is their true, known history --
everything else new is left null/unclassified rather than invented.

Revision ID: 481faa86f41c
Revises: a4d9e6c1f708
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "481faa86f41c"
down_revision = "a4d9e6c1f708"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("locations", sa.Column("provider", sa.String(length=30), nullable=True))
    op.add_column("locations", sa.Column("external_place_id", sa.String(length=255), nullable=True))
    op.add_column("locations", sa.Column("google_primary_type", sa.String(length=100), nullable=True))
    op.add_column("locations", sa.Column("google_types", postgresql.JSONB(), nullable=True))
    op.add_column("locations", sa.Column("category", sa.String(length=50), nullable=True))
    op.add_column("locations", sa.Column("subcategory", sa.String(length=50), nullable=True))
    op.add_column("locations", sa.Column("formatted_address", sa.String(length=500), nullable=True))

    # True history for existing discovered rows -- they really did come from
    # the (now retired) OpenStreetMap pipeline.
    op.execute("UPDATE locations SET provider = 'openstreetmap' WHERE source = 'discovered' AND provider IS NULL")

    op.create_unique_constraint(
        "uq_locations_provider_external_place_id",
        "locations",
        ["provider", "external_place_id"],
    )
    # Supports the trigram name-similarity dedup check in poi_discovery.py --
    # pg_trgm itself has been enabled since this project's very first migration.
    op.execute("CREATE INDEX ix_locations_name_trgm ON locations USING gin (name gin_trgm_ops)")

    op.add_column("submissions", sa.Column("external_place_id", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("submissions", "external_place_id")

    op.execute("DROP INDEX IF EXISTS ix_locations_name_trgm")
    op.drop_constraint("uq_locations_provider_external_place_id", "locations", type_="unique")
    op.drop_column("locations", "formatted_address")
    op.drop_column("locations", "subcategory")
    op.drop_column("locations", "category")
    op.drop_column("locations", "google_types")
    op.drop_column("locations", "google_primary_type")
    op.drop_column("locations", "external_place_id")
    op.drop_column("locations", "provider")
