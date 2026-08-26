import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# A third, independent state machine (Step 9) alongside the mobile app's own
# sync_status ("did the server receive this?") and Transcription.status ("did AI
# turn audio into text?"). This one answers "did LLM processing turn resolved
# source text into structured observations?"
#   pending:    submission has (or may have) usable source text; extraction has
#               not started.
#   processing: an LLM request is currently in flight for this submission.
#   completed:  validated observations were persisted (zero or more).
#   failed:     the last attempt failed; retryable via POST .../extract.
EXTRACTION_STATUSES = ("pending", "processing", "completed", "failed")


class Extraction(Base):
    """LLM structured-extraction lifecycle for one Submission's resolved source
    text (a note's text_content, or a voice submission's completed transcript).

    A separate entity, not columns on Submission or Transcription -- mirrors why
    Transcription itself is separate from Submission (see
    app/db/models/transcription.py): this is a different lifecycle again, with
    its own retries/errors/provider metadata, and the natural place for a later
    re-extraction concept to attach. One row per submission (submission_id is
    unique); retry mutates this same row rather than creating attempt-history
    rows, matching Transcription's convention.

    Unlike Transcription -- created eagerly the moment audio is attached -- this
    row is created lazily, on the first POST .../extract. There is no system
    event equivalent to "audio arrived" for extraction: both notes (text
    available immediately) and voice (text available only once transcription is
    separately, explicitly completed) are extracted only on an explicit user
    action, never automatically.
    """

    __tablename__ = "extractions"
    __table_args__ = (Index("ix_extractions_status", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # Plain string (not a foreign key/enum table) for the same reason as
    # Transcription.provider -- exactly one provider today, minimal structure to
    # not preclude a second provider later.
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="anthropic")
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Safe, user/operator-facing message only -- never the API key, never raw
    # provider internals. See services/extraction/anthropic_provider.py.
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
