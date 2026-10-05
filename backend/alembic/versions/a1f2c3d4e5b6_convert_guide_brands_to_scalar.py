"""convert guide brands to scalar

Guides can only ever belong to ONE tour-operator brand (BaseCampTours/BCT,
HimalayanWonders/HW, TrekkingHero/TH, PatagoniaHero/PH) -- the mobile app's
multi-select was replaced with a single-select, so the backend column follows:
a plain nullable `brand` string column replaces the JSONB `brands` list added
in 5cc1f4b8bf61.

Data-preserving, not purely additive: any guide that already has one or more
brands recorded keeps the FIRST one (arbitrary tie-break for the rare case of
more than one -- there is no "correct" choice once multi-select is gone, and
silently dropping the field entirely would lose real, if unusual, data for no
reason). A guide with brands = NULL stays NULL. Downgrade performs the
reverse, wrapping the single value back into a one-element list.

Revision ID: a1f2c3d4e5b6
Revises: 5cc1f4b8bf61
Create Date: 2026-10-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1f2c3d4e5b6'
down_revision: Union[str, None] = '5cc1f4b8bf61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('guides', sa.Column('brand', sa.String(length=16), nullable=True))
    op.execute(
        """
        UPDATE guides
        SET brand = brands ->> 0
        WHERE brands IS NOT NULL AND jsonb_array_length(brands) > 0
        """
    )
    op.drop_column('guides', 'brands')


def downgrade() -> None:
    op.add_column('guides', sa.Column('brands', postgresql.JSONB(), nullable=True))
    op.execute(
        """
        UPDATE guides
        SET brands = to_jsonb(ARRAY[brand])
        WHERE brand IS NOT NULL
        """
    )
    op.drop_column('guides', 'brand')
