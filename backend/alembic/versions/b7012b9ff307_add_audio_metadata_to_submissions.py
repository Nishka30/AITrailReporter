"""add audio metadata to submissions

Revision ID: b7012b9ff307
Revises: 74f86d4e7056
Create Date: 2026-08-26 15:47:38.203819

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7012b9ff307'
down_revision: Union[str, None] = '74f86d4e7056'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('submissions', sa.Column('client_audio_id', sa.String(length=255), nullable=True))
    op.add_column('submissions', sa.Column('audio_storage_key', sa.String(length=500), nullable=True))
    op.add_column('submissions', sa.Column('audio_content_type', sa.String(length=100), nullable=True))
    op.add_column('submissions', sa.Column('audio_original_filename', sa.String(length=255), nullable=True))
    op.add_column('submissions', sa.Column('audio_size_bytes', sa.Integer(), nullable=True))
    op.add_column('submissions', sa.Column('audio_duration_seconds', sa.Numeric(precision=10, scale=3), nullable=True))
    op.create_unique_constraint(
        'uq_submissions_client_audio_id', 'submissions', ['client_audio_id']
    )


def downgrade() -> None:
    op.drop_constraint('uq_submissions_client_audio_id', 'submissions', type_='unique')
    op.drop_column('submissions', 'audio_duration_seconds')
    op.drop_column('submissions', 'audio_size_bytes')
    op.drop_column('submissions', 'audio_original_filename')
    op.drop_column('submissions', 'audio_content_type')
    op.drop_column('submissions', 'audio_storage_key')
    op.drop_column('submissions', 'client_audio_id')
