"""add client ids for idempotent mobile sync

Revision ID: 267b83a63bb4
Revises: f73d25cbe979
Create Date: 2026-08-26 14:30:22.278396

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '267b83a63bb4'
down_revision: Union[str, None] = 'f73d25cbe979'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('guides', sa.Column('client_guide_id', sa.String(length=255), nullable=True))
    op.create_unique_constraint('uq_guides_client_guide_id', 'guides', ['client_guide_id'])
    op.add_column('submissions', sa.Column('client_submission_id', sa.String(length=255), nullable=True))
    op.create_unique_constraint(
        'uq_submissions_client_submission_id', 'submissions', ['client_submission_id']
    )


def downgrade() -> None:
    op.drop_constraint('uq_submissions_client_submission_id', 'submissions', type_='unique')
    op.drop_column('submissions', 'client_submission_id')
    op.drop_constraint('uq_guides_client_guide_id', 'guides', type_='unique')
    op.drop_column('guides', 'client_guide_id')
