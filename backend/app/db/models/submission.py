import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


@dataclass
class SubmissionAudioMetadata:
    """Plain (non-mapped) view of a submission's audio_* columns, exposed via
    Submission.audio below so app/schemas/submission.py can serialize it as a
    nested object without duplicating the flat-vs-nested mapping logic there."""

    content_type: str
    original_filename: str
    size_bytes: int
    duration_seconds: float | None


@dataclass
class SubmissionPhotoMetadata:
    """Same idea as SubmissionAudioMetadata, for Step 16's Explore photos.
    Deliberately has no duration field — a photo has none, and fabricating a
    shared shape across the two media kinds would be dishonest."""

    content_type: str
    original_filename: str
    size_bytes: int


class Submission(Base):
    """Raw, historical submission from a guide, prior to any structured extraction."""

    __tablename__ = "submissions"
    __table_args__ = (
        Index("ix_submissions_source_question_id", "source_question_id"),
        Index("ix_submissions_source_place_question_id", "source_place_question_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    guide_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("guides.id", ondelete="CASCADE"), nullable=False
    )
    # Provenance (Step 13, Part E): set only for submission_type == 'answer' --
    # traces this submission back to the Question it was generated from
    # answering. SET NULL (not CASCADE) on delete: a Question is not expected
    # to ever be deleted in this project, but if it were, the historical
    # submission/observations it produced should survive as orphaned-but-intact
    # records, not be destroyed along with it.
    source_question_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="SET NULL"), nullable=True
    )
    # Provenance (Step 18): the popular/researched question this submission
    # answers, when it came from that SECOND question source rather than the
    # knowledge-gap queue. Mutually exclusive with source_question_id in
    # practice -- a submission answers one or the other, never both -- but that
    # is an application-level truth, not a DB constraint, matching how the rest
    # of this schema treats mutually-exclusive optional provenance.
    #
    # SET NULL (not CASCADE) for the same reason as source_question_id above:
    # if a place question were ever deleted, the historical submission and the
    # observations it produced must survive as orphaned-but-intact records.
    # (In practice a superseded place question is deactivated, never deleted --
    # see app/db/models/place_question.py.)
    source_place_question_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("place_questions.id", ondelete="SET NULL"), nullable=True
    )
    # Stable client-generated id (e.g. a mobile app's local UUID) used to make
    # submission ingestion idempotent. Nullable for the same reason as
    # Guide.client_guide_id; a unique index enforces "same client id -> same
    # submission" whenever it is supplied.
    client_submission_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submission_type: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="received")
    # Audio metadata (Step 7). All nullable — only populated once a "voice"
    # submission's audio has actually been uploaded and durably stored; a voice
    # submission with these still null means "metadata created, audio not received
    # yet" (mirrors the mobile local capture's own pending -> uploaded lifecycle).
    #
    # client_audio_id is a second, distinct stable client-generated id from
    # client_submission_id: it makes the *audio attachment step* independently
    # idempotent/retryable, since submission creation and audio upload are two
    # separate requests (see services/submissions.py:attach_audio_to_submission).
    client_audio_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    # Server-generated storage key (never a client-supplied path) resolved through
    # app/services/storage/ — never exposed to clients directly, see SubmissionRead.
    audio_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    audio_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    audio_original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    audio_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    audio_duration_seconds: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    # Photo metadata (Step 16). Exactly the same lifecycle and idempotency shape
    # as the audio_* columns above: all nullable, only populated once an Explore
    # photo has actually been uploaded and durably stored. client_photo_id is a
    # third distinct stable client id (alongside client_submission_id and
    # client_audio_id) making the photo attachment step independently
    # idempotent/retryable.
    #
    # A submission carries at most one photo. Audio and photo columns are
    # independent, so nothing structurally prevents a future submission type
    # from having both — but no current flow produces that.
    client_photo_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    # Server-generated storage key (never a client-supplied path) resolved through
    # app/services/storage/ — never exposed to clients directly, see SubmissionRead.
    photo_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    photo_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    photo_original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    photo_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    @property
    def audio(self) -> SubmissionAudioMetadata | None:
        """None until audio has actually been uploaded (audio_storage_key set) —
        never fabricates metadata for a voice submission that's still pending its
        audio upload."""
        if self.audio_storage_key is None:
            return None
        return SubmissionAudioMetadata(
            content_type=self.audio_content_type,
            original_filename=self.audio_original_filename,
            size_bytes=self.audio_size_bytes,
            duration_seconds=(
                float(self.audio_duration_seconds)
                if self.audio_duration_seconds is not None
                else None
            ),
        )

    @property
    def photo(self) -> SubmissionPhotoMetadata | None:
        """None until a photo has actually been uploaded (photo_storage_key set)
        — same honesty rule as `audio` above: an Explore submission whose photo
        upload hasn't landed yet reports None rather than a hollow object."""
        if self.photo_storage_key is None:
            return None
        return SubmissionPhotoMetadata(
            content_type=self.photo_content_type,
            original_filename=self.photo_original_filename,
            size_bytes=self.photo_size_bytes,
        )
