import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Mirrors PlaceQuestionResearch's lifecycle vocabulary (see place_question.py)
# for the same reason: 'pending' before anything has ever run, 'completed' for
# the last successful generation, 'failed' when the last attempt didn't
# produce usable output. There is no 'processing' state here -- unlike
# PlaceQuestionResearch, this never needs its own claim/lock: it is only ever
# generated from INSIDE place_questions.ensure_researched, which has already
# taken that lock and released it before any external call, so there is no
# second concurrent entry point to race against.
LOCATION_RESEARCH_SUMMARY_STATUSES = ("pending", "completed", "failed")


class LocationResearchSummary(Base):
    """A reusable, structured, WEB-RESEARCHED summary of one Location --
    description, highlights, practical info, warnings, categories --
    generated for the future Travelers website so it can show something
    useful about a place before TrailMind has any guide contributions there.

    WHERE THIS FITS: piggybacks on place_questions.ensure_researched's
    existing Perplexity findings for this Location, RIGHT AFTER they are
    persisted (see place_summary_service.maybe_generate_summary) -- it never
    runs its own web search, so it costs nothing extra in Perplexity spend and
    inherits that function's existing place_question_refresh_days cooldown and
    concurrency lock for free rather than duplicating either. One row per
    Location (upserted in place on each regeneration, not append-only like
    PlaceResearchFinding), because only the CURRENT summary is ever useful to
    a reader -- there is no reason to keep every past version.

    TRUST BOUNDARY, ENFORCED STRUCTURALLY: this is WEB-RESEARCHED CONTENT,
    never TrailMind-verified knowledge. It is a SEPARATE table from
    CategoryKnowledge specifically so that boundary cannot be blurred by a
    forgotten WHERE clause -- nothing outside place_summary_service ever
    writes to this table, and nothing in this table ever feeds into
    CategoryKnowledge (only a moderated guide-answered Observation does that;
    see extractions.py). A reader combining this with CategoryKnowledge and
    live conditions must be able to tell, from the shape of the response
    alone, which is which.
    """

    __tablename__ = "location_research_summaries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # UNIQUE: one summary per Location, upserted in place -- see class
    # docstring for why this differs from PlaceResearchFinding's append-only
    # shape.
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Structured content -- all nullable: a 'failed' or not-yet-run row
    # has none of these, and even a successful run may honestly have nothing
    # for a given field (research doesn't always cover every angle). Never
    # invented to fill a gap -- see place_summary/prompt.py.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    known_for: Mapped[str | None] = mapped_column(Text, nullable=True)
    highlights: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    things_to_do: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    important_facts: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    practical_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Real, openable citations -- same parallel-array convention as
    # PlaceResearchFinding, and same anti-hallucination rule: every URL here
    # was verified to be one this Location's findings actually returned (see
    # place_summary/validation.py's citation allowlist check).
    source_urls: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    source_titles: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Cost/usage provenance for the generation call, copied verbatim from the
    # provider's own response -- same convention as PlaceResearchFinding.
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)

    # Only a SUCCESSFUL generation moves this -- mirrors
    # PlaceQuestionResearch.researched_at exactly, so "how stale is this
    # place's public summary" is answerable the same way "how stale is its
    # question research" already is (they move together, since one triggers
    # the other).
    researched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
