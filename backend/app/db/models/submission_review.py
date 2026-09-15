import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Mirrors observation_moderation.MODERATION_STATUSES exactly -- same three
# states, same meanings, applied one level up the pipeline: this is "does a
# human get paid for this CONTRIBUTION", where ObservationModeration is "is
# this EXTRACTED FACT fit for public visibility". The two are deliberately
# separate tables (see the module docstring below) even though the vocabulary
# is identical, because a Submission can produce zero, one, or many
# Observations, and reward-granting has to be decided at the Submission/answer
# level regardless of how many (if any) Observations eventually exist.
SUBMISSION_REVIEW_STATUSES = ("pending_review", "approved", "rejected")

# Same closed vocabulary as ObservationModeration.REJECTION_REASONS (kept as
# an independent copy, not an import, because these two tables are reviewing
# genuinely different things -- a knowledge-quality decision vs. a
# contribution-worth-paying-for decision -- even though today's UI reuses the
# same picker). Values intentionally identical so the SAME admin
# DecisionDialog component works for both without modification.
REJECTION_REASONS = ("inaccurate", "unsafe", "duplicate", "poor_quality", "not_useful", "other")


class SubmissionReview(Base):
    """Whether ONE Submission/answer is approved to be PAID for.

    THE PROBLEM THIS SOLVES: reward_ledger rows were historically inserted the
    instant a submission/answer was stored (see app/services/rewards.py),
    before extraction even ran -- there was no gate of any kind between "a
    guide submitted something" and "the guide was paid for it". This table is
    that gate: reward_service.award(...) is no longer called at submission
    time; instead ensure_pending_review() is, and the actual award() call
    moves to approve() in app/services/submission_review.py, firing exactly
    once no matter how many times approval is (re)requested.

    WHY THIS IS A SEPARATE TABLE FROM ObservationModeration, not a reuse of
    it: ObservationModeration is 1:1 with an Observation, and one Submission
    can yield zero, one, or many Observations (extraction can fail, or
    legitimately complete with zero observations -- see extractions.py).
    Reward-granting needs exactly one decision per rewarded action
    (submission or answer), so it needs its own 1:1-with-Submission table
    rather than being derived from a variable-cardinality relationship. The
    two systems review genuinely different things -- "is this knowledge
    accurate enough to publish" vs. "is this contribution worth paying for"
    -- and are allowed to disagree: a submission can be paid (a guide made a
    good-faith, verifiable report) even if none of what it contains survives
    knowledge moderation, and vice versa is equally possible in principle.

    Only created for submissions/answers that are actually reward-eligible
    (see the three call sites in submissions.py/question_answers.py/
    place_question_answers.py) -- a plain 'note' or unprompted 'voice'
    submission earns nothing today and never has a row here, exactly
    mirroring which submissions call reward_service.award() before this
    feature existed.

    The reward-award parameters (`reward_rule_key`, `reward_idempotency_key`,
    `reward_source_type`, `reward_source_id`) are captured HERE, at creation
    time, rather than re-derived at approval time -- so approve() is a pure
    "replay these exact, already-decided arguments into award()" operation
    with no risk of resolving a different rule/kind than the one the guide
    actually earned. `reward_idempotency_key` is the SAME key that would have
    gone directly into reward_ledger.idempotency_key before this feature
    existed (client_submission_id / client_answer_id) -- moving the award
    call to approval time changes WHEN it fires, never the uniqueness domain
    that makes double-awarding structurally impossible.
    """

    __tablename__ = "submission_reviews"
    __table_args__ = (
        Index("ix_submission_reviews_status_created_at", "status", "created_at"),
        Index("ix_submission_reviews_guide_id", "guide_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    # Denormalized from Submission.guide_id purely so "this guide's pending/
    # approved/rejected contributions" (the guide-facing status endpoint, and
    # admin's per-guide filter) is a plain indexed equality lookup rather than
    # a join for every read of what is, in practice, the single most common
    # query against this table.
    guide_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("guides.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending_review")
    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rejection_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The exact arguments approve() replays into reward_service.award() --
    # see the class docstring for why these are captured now rather than
    # re-derived later.
    reward_rule_key: Mapped[str] = mapped_column(String(100), nullable=False)
    reward_idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    reward_source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    reward_source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Set once, by approve(), to the points reward_service.award() actually
    # returned. Nullable/None for pending or rejected -- 0 is a legitimate
    # award outcome (e.g. the rule was deactivated between submission and
    # approval) and must stay distinguishable from "not decided yet".
    reward_points_awarded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
