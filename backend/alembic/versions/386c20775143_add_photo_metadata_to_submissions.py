"""add photo metadata to submissions

Revision ID: 386c20775143
Revises: e166034d56a0
Create Date: 2026-08-27 14:06:38.898223

Step 16 (Explore): adds the photo_* attachment columns, mirroring the existing
audio_* columns added in b7012b9ff307. Purely additive and fully nullable — no
existing submission row is touched or needs backfilling, because a submission
that predates Explore genuinely has no photo (NULL is the truthful value, not a
"not yet migrated" placeholder).

The unique constraint is named EXPLICITLY (matching the existing
uq_submissions_client_audio_id / uq_submissions_client_submission_id
convention) rather than left to autogenerate's `None`, which would have
produced an undroppable constraint and a broken downgrade().
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '386c20775143'
down_revision: Union[str, None] = 'e166034d56a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CLIENT_PHOTO_ID_UNIQUE = "uq_submissions_client_photo_id"


def upgrade() -> None:
    op.add_column('submissions', sa.Column('client_photo_id', sa.String(length=255), nullable=True))
    op.add_column('submissions', sa.Column('photo_storage_key', sa.String(length=500), nullable=True))
    op.add_column('submissions', sa.Column('photo_content_type', sa.String(length=100), nullable=True))
    op.add_column('submissions', sa.Column('photo_original_filename', sa.String(length=255), nullable=True))
    op.add_column('submissions', sa.Column('photo_size_bytes', sa.Integer(), nullable=True))
    # The real idempotency guarantee for photo upload (see
    # app/services/submissions.py:attach_photo_to_submission) — an application
    # check alone would not survive a concurrent retry.
    op.create_unique_constraint(_CLIENT_PHOTO_ID_UNIQUE, 'submissions', ['client_photo_id'])


def downgrade() -> None:
    op.drop_constraint(_CLIENT_PHOTO_ID_UNIQUE, 'submissions', type_='unique')
    op.drop_column('submissions', 'photo_size_bytes')
    op.drop_column('submissions', 'photo_original_filename')
    op.drop_column('submissions', 'photo_content_type')
    op.drop_column('submissions', 'photo_storage_key')
    op.drop_column('submissions', 'client_photo_id')
