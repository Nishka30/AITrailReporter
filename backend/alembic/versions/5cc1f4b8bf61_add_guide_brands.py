"""add guide brands

Guides can now record which tour-operator brand(s) they belong to
(BaseCampTours/BCT, HimalayanWonders/HW, TrekkingHero/TH, PatagoniaHero/PH).
A guide may belong to more than one brand, so this is a single JSONB list
column (e.g. ["BCT", "HW"]) rather than a scalar column -- see
app/db/models/guide.py's GUIDE_BRANDS for the controlled set of short codes
and app/schemas/guide.py for the validation that keeps the column restricted
to those codes and de-duplicated. Postgres JSONB itself cannot enforce that
restriction, so this migration does not attempt a CHECK constraint for it;
enforcement lives entirely in the Pydantic schema, consistent with how every
other string-enum column in this schema (location_source, submission status,
etc.) is validated at the application layer rather than the DB layer.

Purely additive: a new nullable column with no default. Existing guides keep
brands = NULL, which is the truthful value for a guide that recorded no brand
information before this feature existed -- this migration creates structure
only, it never invents or backfills application content.

Revision ID: 5cc1f4b8bf61
Revises: b4d8f2a6c9e1
Create Date: 2026-10-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '5cc1f4b8bf61'
down_revision: Union[str, None] = 'b4d8f2a6c9e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('guides', sa.Column('brands', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('guides', 'brands')
