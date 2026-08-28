import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# A SIXTH independent state machine, alongside the mobile app's own
# sync_status, Transcription.status, Extraction.status, Question.status, and
# QuestionAssignment.status. This one answers a question none of the others
# do: "has a human decided this piece of knowledge is fit to eventually reach
# the public app?" Nothing about extraction succeeding, transcription
# succeeding, or knowledge freshness implies an answer here -- those are
# orthogonal questions about DIFFERENT lifecycles.
#
#   pending_review: the default state, set the moment an Observation is
#                    created (see app/services/extractions.py) -- there is
#                    never a window where an Observation exists with no
#                    moderation row.
#   approved:        an admin has reviewed the evidence and approved this
#                    observation for eventual public visibility.
#   rejected:        an admin has reviewed the evidence and rejected it;
#                    rejection_reason records why. The source Submission and
#                    Observation are NEVER deleted or altered by a rejection.
MODERATION_STATUSES = ("pending_review", "approved", "rejected")

# A small, closed set rather than free text -- keeps the review queue
# analyzable ("how many rejections were for safety reasons this month") and
# matches this codebase's convention of enumerations over free-form strings
# wherever the value is later going to be filtered/counted/branched on.
REJECTION_REASONS = ("inaccurate", "unsafe", "duplicate", "poor_quality", "not_useful", "other")


class ObservationModeration(Base):
    """Whether ONE Observation is approved for eventual public visibility.

    Deliberately a separate table from Observation, one row per observation
    (enforced by the UNIQUE constraint below), rather than status columns
    added directly to Observation -- mirrors why Transcription/Extraction/
    Question/QuestionAssignment are each their own table in this codebase: a
    genuinely different lifecycle, with its own actor (an admin, not a
    guide/AI), its own metadata (decided_by, decided_at, rejection_reason),
    and its own future growth path (re-review), rather than a pile of
    nullable-until-reviewed columns bolted onto the row that represents "what
    the AI extracted."

    `decided_by` is a plain string, not a foreign key to an admin-accounts
    table, because no such table exists yet -- there is no real admin
    authentication in this system yet (see app/core/admin_auth.py). It holds
    whatever display name the minimal dev-safe admin boundary identifies the
    reviewer as, and is meant to become a real foreign key once proper admin
    accounts exist -- that migration would not need to change this table's
    shape.
    """

    __tablename__ = "observation_moderation"
    __table_args__ = (
        Index("ix_observation_moderation_status_created_at", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    observation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("observations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending_review")
    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rejection_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
