import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Every place a reward can be earned. Kept as a tuple here (and seeded as rows
# in reward_rules) rather than hardcoded numbers anywhere: the mobile app never
# decides what an answer is worth, it only DISPLAYS what the backend already
# told it (see app/api/routes/rewards.py). Adding a new earning opportunity
# later is an INSERT, not a code change -- which is the whole point of
# reward_rules being a table rather than a config constant.
REWARD_RULE_KEYS = (
    "question_answer",
    "question_answer_safety_critical",
    # Fallback rate for a place-question contribution whose kind has no active
    # rule of its own. Kept because place_questions.contribution_kind can hold a
    # kind added later whose rule hasn't been seeded yet -- falling back to a
    # real configured rate is honest; inventing a number in code is not.
    "place_question_answer",
    # Per-kind rates. These exist because the kinds genuinely differ in effort:
    # taking and describing a photo on the spot is more work than confirming
    # whether a tea stall is open. See PLACE_QUESTION_CONTRIBUTION_KINDS.
    "place_question_photo",
    "place_question_voice",
    "place_question_experience",
    "place_question_observation",
    "place_question_status",
    "explore_contribution",
    # An ADDITIVE bonus on top of explore_contribution, not a replacement
    # rate. Modelled this way because media arrives in a SEPARATE later
    # request than the submission it attaches to, so the base award is already
    # committed by then. A bonus row can simply be added; rewriting the
    # original award would mean mutating a ledger entry, which this ledger
    # does not permit. It also keeps the invariant that every row's `points`
    # equals its rule's `points` exactly.
    "explore_contribution_media_bonus",
)

# What produced a ledger entry. Recorded alongside source_id so any award can
# be traced back to the exact answer/submission that earned it.
REWARD_SOURCE_TYPES = ("question_answer", "place_question_answer", "explore_submission")


class RewardRule(Base):
    """How many points one kind of contribution is worth.

    A table rather than constants in config so the values can change without a
    deploy, and so "different rewards based on question type/importance" is a
    new ROW rather than a new branch in code. `rule_key` is the stable
    identifier the services resolve against (see app/services/rewards.py);
    `points` is the only thing that ever needs editing operationally.

    Deactivating a rule (active=False) does not retroactively change ledger
    entries already awarded under it -- the ledger stores the points it
    actually granted, so history stays truthful after a rate change.
    """

    __tablename__ = "reward_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    rule_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class RewardLedger(Base):
    """An append-only record of every reward a guide has earned.

    APPEND-ONLY BY DESIGN: a guide's balance is SUM(points) over their rows,
    never a mutable counter on `guides`. A counter can drift, can be
    double-incremented by a retry, and loses the ability to answer "where did
    these points come from" -- a ledger cannot.

    `idempotency_key` is the entire duplicate-prevention mechanism, and it is
    deliberately NOT a new id: it reuses the client-generated id that already
    flows through this system for the action being rewarded --
    `client_answer_id` for a question/popular-question answer,
    `client_submission_id` for an Explore contribution. Those are already
    unique, already generated once on the device, and already what makes the
    underlying answer/submission itself idempotent.

    That gives the exact guarantee the offline flow needs. A guide answers with
    no signal; the answer and its award are written in ONE transaction when it
    finally syncs; a retried or duplicated sync hits this UNIQUE constraint and
    awards nothing further (see app/services/rewards.py:award, which uses
    ON CONFLICT DO NOTHING). Syncing the same answer three times pays exactly
    once -- and because the local row survives until the server confirms it, an
    offline guide can never LOSE an earned reward either.
    """

    __tablename__ = "reward_ledger"
    __table_args__ = (
        # Supports the balance/history query: WHERE guide_id = ? ORDER BY
        # awarded_at DESC. Ascending column order despite the DESC read, same
        # as ix_observations_knowledge_type_id_observed_at -- Postgres serves
        # it via a backward index scan.
        Index("ix_reward_ledger_guide_id_awarded_at", "guide_id", "awarded_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    guide_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("guides.id", ondelete="CASCADE"), nullable=False
    )
    # The points actually granted, copied from the RewardRule at award time --
    # NOT looked up live. A later rate change must never silently rewrite what
    # a guide already earned.
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_key: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    awarded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
