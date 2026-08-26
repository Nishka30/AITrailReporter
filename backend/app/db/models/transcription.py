import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Precise, deliberately distinct from the mobile app's sync_status
# (pending/uploading/uploaded/failed — "did the server receive the audio?").
# This state machine answers a different question: "did AI processing turn the
# audio into text?"
#   pending:    audio is available, transcription has not started.
#   processing: a Sarvam request is currently in flight for this submission.
#   completed:  a usable transcript was received and persisted.
#   failed:     the last attempt failed; retryable via POST .../transcribe.
TRANSCRIPTION_STATUSES = ("pending", "processing", "completed", "failed")


class Transcription(Base):
    """AI transcription lifecycle for one voice Submission's audio.

    A separate entity from Submission on purpose, not a handful of extra columns
    bolted onto it: Submission answers "what did the guide submit," this answers
    "what did AI processing do with that submission's audio" — a genuinely
    different lifecycle (its own retries, errors, provider metadata), and the
    natural place for a later re-transcription or human-review concept to attach
    without Submission accumulating unrelated state. One row per submission for
    this step (submission_id is unique) — retry mutates this same row rather than
    creating attempt history rows; see backend/README.md for why.
    """

    __tablename__ = "transcriptions"
    __table_args__ = (Index("ix_transcriptions_status", "status"),)

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
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    # What Sarvam detected/used for this attempt — not necessarily what we asked
    # for (we ask for "unknown"/auto-detect; see services/transcription/sarvam.py).
    language_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    language_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Provider metadata. `provider` is a plain string (not a foreign key/enum
    # table) because there is exactly one provider today — this is deliberately
    # the minimal amount of structure to not preclude a second provider later.
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="sarvam")
    model: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # User/operator-safe message only — never the API key, never raw provider
    # internals beyond a short, safe description. See services/transcription/sarvam.py.
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
