"""add client_location_id for idempotent mobile location sync

Revision ID: 74f86d4e7056
Revises: 267b83a63bb4
Create Date: 2026-08-26 15:02:12.590252

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '74f86d4e7056'
down_revision: Union[str, None] = '267b83a63bb4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('guide_locations', sa.Column('client_location_id', sa.String(length=255), nullable=True))
    op.create_unique_constraint(
        'uq_guide_locations_client_location_id', 'guide_locations', ['client_location_id']
    )


def downgrade() -> None:
    op.drop_constraint('uq_guide_locations_client_location_id', 'guide_locations', type_='unique')
    op.drop_column('guide_locations', 'client_location_id')
