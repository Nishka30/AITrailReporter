"""multi-photo: submission_photos table

A submission used to carry at most one photo, via five flat columns
(client_photo_id, photo_storage_key, photo_content_type,
photo_original_filename, photo_size_bytes) directly on `submissions`. This
migration replaces those with a proper child table, `submission_photos`, so a
submission can carry several photos -- mirroring this codebase's existing
"separate lifecycle -> separate entity" convention (Transcription, Extraction,
ObservationModeration are all their own tables rather than columns on their
parent), not a JSONB blob.

Backfill runs BEFORE the old columns are dropped: every submission that
already has a photo gets exactly one `submission_photos` row (position=0),
generated with the same client_photo_id/storage_key/metadata it already had --
no existing photo's storage_key, and therefore no already-uploaded file, is
touched. After the backfill, the five old columns are dropped; Postgres
automatically drops the single-column UNIQUE constraint on client_photo_id
along with it (nothing else references it via FK).

DOWNGRADE IS LOSSY BEYOND THE FIRST PHOTO: if this migration is ever rolled
back after new submissions have accumulated MORE than one photo each, the
old single-photo columns can only hold one photo per submission again -- the
downgrade restores the LOWEST-position (`position` = MIN) photo per
submission and drops the rest from submission_photos before removing the
table. This is an accepted, disclosed trade-off of a genuine cardinality
change (one -> many), not an oversight; the upgrade path never loses data.

Revision ID: 036f23e86de6
Revises: f4daa3cc91fa
Create Date: 2026-09-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "036f23e86de6"
down_revision: Union[str, None] = "f4daa3cc91fa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "submission_photos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_photo_id", sa.String(length=255), nullable=False, unique=True),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["submission_id"], ["submissions.id"],
            name="fk_submission_photos_submission_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_submission_photos_submission_id", "submission_photos", ["submission_id"])

    # Backfill: every submission with an existing single photo gets one
    # position=0 row carrying the EXACT SAME client_photo_id/storage_key/
    # metadata -- the already-uploaded file is never touched or re-uploaded.
    op.execute(
        """
        INSERT INTO submission_photos
            (id, submission_id, client_photo_id, storage_key, content_type,
             original_filename, size_bytes, position, created_at)
        SELECT gen_random_uuid(), s.id, s.client_photo_id, s.photo_storage_key,
               s.photo_content_type, s.photo_original_filename, s.photo_size_bytes,
               0, s.created_at
        FROM submissions s
        WHERE s.photo_storage_key IS NOT NULL
        """
    )

    op.drop_column("submissions", "client_photo_id")
    op.drop_column("submissions", "photo_storage_key")
    op.drop_column("submissions", "photo_content_type")
    op.drop_column("submissions", "photo_original_filename")
    op.drop_column("submissions", "photo_size_bytes")


def downgrade() -> None:
    op.add_column("submissions", sa.Column("client_photo_id", sa.String(length=255), nullable=True))
    op.add_column("submissions", sa.Column("photo_storage_key", sa.String(length=500), nullable=True))
    op.add_column("submissions", sa.Column("photo_content_type", sa.String(length=100), nullable=True))
    op.add_column("submissions", sa.Column("photo_original_filename", sa.String(length=255), nullable=True))
    op.add_column("submissions", sa.Column("photo_size_bytes", sa.Integer(), nullable=True))
    op.create_unique_constraint("uq_submissions_client_photo_id", "submissions", ["client_photo_id"])

    # Restore only the lowest-position ("first") photo per submission -- see
    # this migration's module docstring for why anything beyond that is
    # necessarily lost on downgrade.
    op.execute(
        """
        UPDATE submissions s
        SET client_photo_id = sp.client_photo_id,
            photo_storage_key = sp.storage_key,
            photo_content_type = sp.content_type,
            photo_original_filename = sp.original_filename,
            photo_size_bytes = sp.size_bytes
        FROM (
            SELECT DISTINCT ON (submission_id) submission_id, client_photo_id,
                   storage_key, content_type, original_filename, size_bytes
            FROM submission_photos
            ORDER BY submission_id, position ASC
        ) sp
        WHERE s.id = sp.submission_id
        """
    )

    op.drop_index("ix_submission_photos_submission_id", table_name="submission_photos")
    op.drop_table("submission_photos")
