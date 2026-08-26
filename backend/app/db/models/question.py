import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# A FOURTH independent state machine (Step 12), alongside the mobile app's own
# sync_status, Transcription.status (Step 8), and Extraction.status (Step 9).
# This one answers "did LLM processing turn a knowledge gap into a usable
# question?" -- nothing about whether/who it's assigned to, or whether anyone
# has answered it (see QuestionAssignment for that, a deliberately SEPARATE
# state machine).
#   pending:    row created (a real gap was confirmed at creation time),
#               generation has not been attempted yet.
#   processing: an LLM request is currently in flight for this question.
#   generated:  a validated question_text was produced and persisted.
#   failed:     the last attempt failed (provider error, invalid output, or the
#               underlying gap resolved before/during generation); retryable
#               via POST /api/v1/questions with the same client_request_id.
QUESTION_STATUSES = ("pending", "processing", "generated", "failed")


class Question(Base):
    """A generated, persisted question for a trek guide, derived from one
    ranked knowledge gap (Step 10 + Step 11) at generation time.

    Deliberately its own entity, not columns on Observation/KnowledgeTypeConfig
    or a row inside the (ephemeral, computed-live) knowledge-decision result --
    mirrors why Transcription/Extraction are their own tables: a genuinely
    different lifecycle (its own retries/errors/provider metadata), and unlike
    those two, there is no natural pre-existing row (like a Submission) to hang
    this off of, since a "gap" is not itself a persisted entity. The gap's
    identifying and ranking context is therefore SNAPSHOTTED onto this row at
    creation time (gap_state, target_latitude/longitude, safety_critical,
    default_priority, staleness_severity_hours, gap_rank,
    nearest_known_place_*) -- Step 10/11 remain the source of truth for
    freshness/ranking logic itself; this table only ever stores a point-in-time
    copy of their output, never recomputes it.
    """

    __tablename__ = "questions"
    __table_args__ = (Index("ix_questions_status", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Caller-supplied stable idempotency key (Step 12's version of
    # client_submission_id/client_guide_id/client_audio_id/client_location_id).
    # Nullable: a caller that doesn't supply one gets no idempotency (always
    # creates fresh), matching client_location_id's optional behavior.
    client_request_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)

    knowledge_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_type_config.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Snapshot of the gap's state AT GENERATION TIME -- 'missing', 'stale', or
    # (Step 14) 'aging'. Never 'fresh' (a fresh knowledge type is not a gap
    # and can't produce a Question in the first place). This is a POINT-IN-TIME
    # snapshot, never recomputed -- a Question generated while the gap was
    # 'aging' keeps reading 'aging' forever, even if live knowledge state later
    # reclassifies it as 'stale' or 'fresh' (see app/services/questions.py).
    gap_state: Mapped[str] = mapped_column(String(20), nullable=False)

    # No `geog` column here (unlike Observation/Location/GuideLocation) --
    # deliberately: nothing in this step queries Question spatially (no
    # "questions near me" endpoint exists yet), and Submission.latitude/
    # longitude is the existing precedent in this codebase for a coordinate
    # pair stored as plain columns without PostGIS geography when nothing yet
    # needs a spatial query against it. Add geog + an index exactly when a
    # real query needs it, not before.
    target_latitude: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    target_longitude: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)

    # Snapshot from geographic_context_service.resolve_geographic_context at
    # generation time -- a denormalized copy (name + distance), not a live FK
    # to `locations`, so this question's historical record never silently
    # changes meaning if that Location row is later renamed/removed.
    nearest_known_place_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nearest_known_place_distance_meters: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Snapshot of ranking provenance from Step 11 -- Step 11 remains the ONLY
    # place that computes ranking; these columns just preserve WHY this
    # question was generated, per this step's explicit requirement (Part G).
    safety_critical: Mapped[bool] = mapped_column(Boolean, nullable=False)
    default_priority: Mapped[int] = mapped_column(Integer, nullable=False)
    staleness_severity_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    gap_rank: Mapped[int] = mapped_column(Integer, nullable=False)

    # Populated only once status == 'generated'.
    question_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    short_context: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # Plain string, same reasoning as Transcription.provider/Extraction.provider
    # -- exactly one provider today.
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="anthropic")
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Safe, user/operator-facing message only -- never the API key, never raw
    # provider internals. See services/question_generation/anthropic_provider.py.
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
