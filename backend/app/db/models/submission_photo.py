import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SubmissionPhoto(Base):
    """One durably-stored photo attached to a submission -- a submission may
    now carry SEVERAL of these (multi-image support), replacing the earlier
    single `photo_*`/`client_photo_id` columns that used to live directly on
    `Submission` (see the migration that introduced this table for the
    backfill of pre-existing single-photo data).

    Deliberately its own table rather than a JSONB array column on
    `Submission`: each photo needs its own idempotency key
    (`client_photo_id`), its own storage key, and its own metadata -- exactly
    the same "separate lifecycle -> separate entity" reasoning this codebase
    already applies to Transcription/Extraction/ObservationModeration, not a
    blob of loosely-typed data.

    `client_photo_id` stays GLOBALLY unique (not just unique per submission),
    mirroring the single-column convention it replaces: it is a client-
    generated id from ONE physical capture, and a client never has a reason
    to reuse it across two different photos.

    `position` records the order photos were attached in (0-based), purely
    for stable display order -- it carries no other meaning and is never
    read by anything that decides sync/upload behavior.
    """

    __tablename__ = "submission_photos"
    __table_args__ = (
        Index("ix_submission_photos_submission_id", "submission_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False
    )
    client_photo_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    # Server-generated storage key (never a client-supplied path) resolved
    # through app/services/storage/ -- never exposed to clients directly.
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
