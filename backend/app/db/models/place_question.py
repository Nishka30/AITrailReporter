import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


# How the guide is being asked to answer -- chosen PER PLACE by the research
# step, not applied uniformly. A suspension bridge earns a photo request; a tea
# stall earns "is it open right now"; a viewpoint earns "can you see it today".
# Forcing every place through one template is exactly what this list exists to
# prevent.
#
# Each kind maps to its own reward_rules row (see app/services/rewards.py:
# place_question_rule_key), because the kinds genuinely differ in effort: a
# photo taken on the spot is worth more than a yes/no status check.
PLACE_QUESTION_CONTRIBUTION_KINDS = (
    # "Can you show us what this looks like today?"
    "photo",
    # "Tell us what your experience here was like."
    "voice",
    # "What do you notice here right now?"
    "observation",
    # "What is this place actually like?"
    "experience",
    # "Is it open / accessible / busy right now?"
    "status",
)

DEFAULT_CONTRIBUTION_KIND = "observation"


class PlaceQuestion(Base):
    """A location-specific invitation to contribute about a known Location,
    researched from the web -- the SECOND, secondary question source.

    WHAT THIS IS NOT (corrected after the first implementation): it is not a
    traveller FAQ about the place. "Is it safe to cross the Hillary Bridge if
    you're scared of heights?" is a question for a READER; it is useless to ask
    a guide standing on that bridge. What belongs here is the second-person,
    present-tense form of the same research: "You're right by Hillary Bridge --
    how does it look today?". The web research establishes what people actually
    care about at this exact place; the invitation asks the person who is
    physically there to answer it from what they can see.

    Deliberately NOT a row in `questions`. A Question is structurally welded to
    a knowledge gap: knowledge_type_id (NOT NULL, FK RESTRICT), gap_state (NOT
    NULL, and only ever 'missing'/'stale'/'aging'), plus the gap_rank /
    staleness_severity_hours / default_priority / safety_critical provenance
    snapshot taken at generation time. A popular question has NONE of those --
    it is not derived from a gap, is not ranked, and is never assigned to a
    specific guide. Reusing `questions` would have meant making roughly six
    NOT NULL columns nullable and letting rows that were never gaps sit inside
    the gap-ranking system. Following this codebase's established
    "separate lifecycle -> separate entity" rule (the same reasoning that put
    moderation in observation_moderation rather than on observations), it gets
    its own table.

    What it deliberately DOES share: answering one produces an ordinary
    Submission which flows through the EXISTING extraction -> observation ->
    moderation pipeline entirely unmodified (see
    app/services/place_question_answers.py). There is no second knowledge
    system.

    `source_urls` holds the real citations the web-search tool returned for
    this batch. It exists so the provenance of a researched question is
    inspectable and never has to be taken on trust -- if research found
    nothing, no row is written at all rather than a question with no source.
    """

    __tablename__ = "place_questions"
    __table_args__ = (
        # Dedup enforced by the DATABASE, not just by application logic --
        # the same discipline every client_*_id in this schema uses.
        # `normalized_text` (see app/services/place_questions.py) collapses
        # case, punctuation and filler words, so "Is it safe to cross?" and
        # "is it safe to cross" can never both be stored for one place.
        UniqueConstraint("location_id", "normalized_text", name="uq_place_questions_location_normalized"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="CASCADE"), nullable=False
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    # One of PLACE_QUESTION_CONTRIBUTION_KINDS. Drives BOTH what the app offers
    # (camera foregrounded for 'photo', recorder for 'voice') and what the
    # contribution is worth -- the reward is looked up from this, never sent by
    # the app. Server_default 'observation' so the column could be added
    # NOT NULL without a data migration guessing at intent for existing rows.
    contribution_kind: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=DEFAULT_CONTRIBUTION_KIND
    )
    # A short grounded line explaining WHY this place is worth reporting on --
    # "people often mention how much this bridge sways". Must come from what
    # research actually found; null when nothing specific was established.
    # Never a generic filler sentence, because a fabricated reason is worse
    # than no reason (see the prompt's rules).
    context_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Display order within one research batch, as ranked by the research step
    # (most commonly asked first). Not a priority in the knowledge-gap sense --
    # popular questions are never ranked against gaps.
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_urls: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # The specific research finding that justified asking this. `source_urls`
    # answers "what backs this up?"; this answers the stronger question "which
    # piece of research, run with which query, produced this?" -- following it
    # reaches the exact text and citations the generation step was reasoning
    # over (see app/db/models/place_research_finding.py).
    #
    # Nullable, and ON DELETE SET NULL: questions researched before findings
    # were recorded have none, and a question must never be destroyed by the
    # removal of its provenance row.
    source_finding_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("place_research_findings.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Groups every question produced by ONE research run, so a refresh can
    # deactivate a previous batch wholesale without deleting history.
    research_batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Set False rather than deleting when a refresh supersedes a question --
    # an already-answered question must never vanish from its answer's
    # provenance (submissions.source_place_question_id is ON DELETE SET NULL
    # precisely so history survives, but keeping the row is better still).
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


# A SEVENTH independent state machine (see observation_moderation.py's comment
# for the existing six). This one answers: "have we researched what people
# commonly ask about this place, and did it succeed?" Structurally identical
# to Transcription.status / Extraction.status / Question.status on purpose --
# same claim/attempt/retry shape, same honest 'failed' state.
PLACE_QUESTION_RESEARCH_STATUSES = ("pending", "processing", "completed", "failed")


class PlaceQuestionResearch(Base):
    """Tracks the web-research lifecycle for ONE Location's popular questions.

    This is what stops the backend re-searching the web on every mobile
    request: `researched_at` records when the last successful run completed,
    and app/services/place_questions.py only starts a new run when there has
    never been one or when it is older than
    `settings.place_question_refresh_days`. One row per Location (UNIQUE),
    retried in place -- exactly how Transcription works per Submission.
    """

    __tablename__ = "place_question_research"
    __table_args__ = (
        # Mirrors ix_transcriptions_status / ix_extractions_status: supports
        # finding rows stuck in a given state ("what research is still
        # processing / has failed").
        Index("ix_place_question_research_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="anthropic")
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # When the last SUCCESSFUL run completed. Distinct from completed_at, which
    # also moves on a failed run -- only this one governs the refresh window,
    # so a string of failures can never look like fresh research.
    researched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
