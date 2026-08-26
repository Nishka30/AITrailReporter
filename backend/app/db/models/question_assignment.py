import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# A FIFTH independent state machine (Step 12), deliberately separate from
# Question.status (see question.py). Question status answers "did generation
# succeed?" -- this answers "what is the guide doing with it?"
#   assigned:  the question was just assigned to this guide. The ONLY status
#              any code in this step ever sets.
#   active:    reserved for a future step where the guide has acknowledged/
#              started responding. Defined now for schema forward-compatibility
#              (per this step's spec) -- no code path in Step 12 sets this.
#   completed: reserved for a future answer workflow (the guide answered).
#              NOT implemented in this step -- see services/questions.py.
#   cancelled: reserved for a future reassignment/retraction flow. NOT
#              triggered by any code in this step.
ASSIGNMENT_STATUSES = ("assigned", "active", "completed", "cancelled")


class QuestionAssignment(Base):
    """One guide's assignment to answer one Question.

    A SEPARATE table from Question, not a guide_id/assigned_at pair of columns
    on Question itself -- deliberately, to support this step's explicit forward
    requirements: a question may eventually be REASSIGNED (a new
    QuestionAssignment row for the same question_id, a different guide_id) and
    assignment HISTORY may matter later (every past assignment attempt stays
    queryable). `question_id` is therefore NOT unique here -- multiple
    assignment rows per question are a valid future shape, unlike
    Transcription/Extraction's one-row-per-submission pattern. In THIS step,
    the actual code only ever creates at most one assignment per question (at
    generation time, inside the same transaction that marks the question
    'generated' -- see services/questions.py), so no reassignment logic exists
    yet; the schema is simply not artificially constrained against it.
    """

    __tablename__ = "question_assignments"
    __table_args__ = (
        Index("ix_question_assignments_guide_id_status", "guide_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    guide_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("guides.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="assigned")
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Never set by any code in this step -- reserved for a future mobile
    # answer workflow (explicitly out of scope here, see Part E of this step's
    # spec: "Do not implement the answer workflow yet").
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
