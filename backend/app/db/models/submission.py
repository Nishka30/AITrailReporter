import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# How a Submission's latitude/longitude came to be, in decreasing order of
# trustworthiness. Follows the same tuple-constant convention as
# app/db/models/location.py's LOCATION_SOURCES.
#
# WHY THIS EXISTS: before this, a Submission's coordinate was either present or
# absent -- nothing recorded WHY it was there, so an old photo uploaded weeks
# later could silently inherit the guide's location at upload time, and an
# Observation built from it would look exactly as trustworthy as one from a
# live GPS-verified capture. This makes that distinction a first-class fact
# instead of something only inferable from context that has since been lost.
SUBMISSION_LOCATION_SOURCES = (
    # From the photo file's own embedded GPS tag -- tied to the pixels
    # themselves, the strongest evidence this system can have.
    "photo_exif",
    # Device GPS read at the moment of capture, for content created here-and-now.
    "gps_live",
    # No direct evidence on the content itself; matched to the guide's own
    # recorded GPS history close in time to when the content actually happened
    # (see app/services/extractions.py:_resolve_observation_coordinates).
    "historical_inferred",
    # The guide picked a real place from a geocoding search -- a human
    # judgement, not a sensor reading.
    "user_selected",
    # A usable but weak signal (e.g. a wide historical match). Deliberately
    # rare: most cases that would otherwise land here are left "unknown"
    # instead -- see historical_location_max_gap_hours.
    "approximate",
    # No usable evidence. The default. Never a fabricated coordinate.
    "unknown",
)
DEFAULT_LOCATION_SOURCE = "unknown"

# How precisely `occurred_at` is actually known -- independent of how
# CONFIDENT the location is, because a guide can be certain of the month a
# memory happened while having no idea exactly where, or vice versa.
DATE_PRECISIONS = ("exact", "month", "year", "approximate", "unknown")
DEFAULT_DATE_PRECISION = "unknown"

# Where `occurred_at` itself came from. "device" means it was taken directly
# from the device clock at capture time (submitted_at), which is exact only
# for a LIVE capture -- for an uploaded-later photo with no EXIF timestamp,
# there is no honest way to know when it happened at all.
DATE_SOURCES = ("device", "exif", "user_entered", "inferred", "unknown")
DEFAULT_DATE_SOURCE = "unknown"


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
    # One of SUBMISSION_LOCATION_SOURCES. NOT NULL with a default of "unknown"
    # rather than nullable: "we don't know how this coordinate was obtained" is
    # a real, queryable state (and the common one for every submission that
    # predates this column), distinct from "there is no coordinate at all"
    # (latitude/longitude both null).
    location_source: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=DEFAULT_LOCATION_SOURCE
    )
    # GPS accuracy in metres, ONLY when a real device/EXIF reading supplied one.
    # Null for historical_inferred/user_selected/approximate -- those have no
    # sensor accuracy figure, and inventing one would overstate precision.
    location_accuracy_meters: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    # When the COORDINATE ITSELF was established -- a device GPS timestamp or
    # an EXIF capture time. Distinct from submitted_at (when it reached the
    # backend) and from occurred_at below (when the CONTENT is about). Null for
    # user_selected/approximate/unknown, which have no such moment.
    location_captured_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # A human-readable place name for admin display without a join -- from a
    # geocoder selection ("Kedarnath Temple") or a reverse-geocode of an
    # inferred point. Never treated as authoritative; the coordinate is.
    location_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # A short, factual note on WHY this location was assigned, e.g. "Matched to
    # a GPS sample 40 min after the photo's timestamp" -- mirrors
    # PlaceQuestion.context_note. Exists so a non-"unknown" location_source is
    # never just an assertion; there is always a stated reason an admin can
    # check.
    location_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    # When the CONTENT is about -- may differ hugely from submitted_at for a
    # photo uploaded long after it was taken. Null means genuinely unknown, not
    # "assume submitted_at" (see occurred_at_precision/date_source).
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # One of DATE_PRECISIONS.
    occurred_at_precision: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=DEFAULT_DATE_PRECISION
    )
    # One of DATE_SOURCES.
    date_source: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=DEFAULT_DATE_SOURCE
    )
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
