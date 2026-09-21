"""add geog to questions (proximity-relevant question surfacing)

Revision ID: f1a2b3c4d5e6
Revises: e7b2c8f14a6d
Create Date: 2026-09-22

Adds a `geog` column to `questions`, exactly the column
app/db/models/question.py's own comment anticipated ("Add geog + an index
exactly when a real query needs it, not before") -- that real query now
exists: surfacing existing, already-generated (possibly stale) questions to
a guide who is near a known Location, without live-recomputing knowledge
state and without a second, competing stale-question system.

Backfilled from target_latitude/target_longitude, which are NOT NULL on
every existing row, so every row gets a geog value with no manual cleanup.
Nullable at the column level regardless (matching Observation's own
nullable=True precedent for a backfilled geography column), since a future
row type is not guaranteed to always have coordinates.

No new table, no location_id FK on Question -- proximity grouping for
display uses the caller's own already-known Location (the selected place),
never a denormalized link stored here (mirrors why nearest_known_place_name
on this same table is a snapshot, not a live FK, per the existing model
docstring).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import geoalchemy2

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e7b2c8f14a6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "questions",
        sa.Column(
            "geog",
            geoalchemy2.types.Geography(
                geometry_type="POINT", srid=4326, from_text="ST_GeogFromText", name="geography"
            ),
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE questions
        SET geog = ST_SetSRID(ST_MakePoint(target_longitude, target_latitude), 4326)::geography
        WHERE geog IS NULL
        """
    )
    op.create_index(
        "ix_questions_geog", "questions", ["geog"], unique=False, postgresql_using="gist"
    )


def downgrade() -> None:
    op.drop_index("ix_questions_geog", table_name="questions")
    op.drop_column("questions", "geog")
