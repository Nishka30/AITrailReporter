import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class QuestionAnswer(Base):
    """A guide's persisted answer to one assigned Question (Step 13).

    A dedicated entity, not columns on Question or QuestionAssignment --
    Question.status already answers "did generation succeed?" and
    QuestionAssignment.status already answers "what is the guide doing with
    it?" (see those models); this answers a third, genuinely different
    question: "what did the guide actually say?" Keeping answer text off
    Question avoids overloading a row whose whole purpose was Step 12's LLM
    generation lifecycle.

    One row per successful answer -- `client_answer_id` is this step's
    version of the established client_submission_id/client_guide_id/
    client_location_id/client_audio_id/client_request_id idempotency
    convention. Unlike some of those (which are optional), it is REQUIRED:
    an answer with no idempotency key at all would let a flaky connection
    silently create two competing answers for the same assignment, which the
    assignment's one-shot 'completed' transition must never allow (see
    services/question_answers.py).
    """

    __tablename__ = "question_answers"
    __table_args__ = (Index("ix_question_answers_question_id", "question_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("question_assignments.id", ondelete="CASCADE"),
        nullable=False,
    )
    guide_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("guides.id", ondelete="CASCADE"), nullable=False
    )
    client_answer_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    # The Submission created from this answer so it can flow through the
    # EXISTING extraction pipeline unmodified (Part E of this step) -- never a
    # second, parallel LLM path. This is the Answer -> Submission direction;
    # Submission.source_question_id (see db/models/submission.py) is the
    # complementary Submission -> Question direction.
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False
    )
    # When the guide actually answered (device-local time), distinct from
    # created_at below -- same submitted_at-vs-created_at distinction used by
    # Submission/GuideLocation.
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
