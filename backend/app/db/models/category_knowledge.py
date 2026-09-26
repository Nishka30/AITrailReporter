import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# One of CATEGORY_KNOWLEDGE_SOURCES. 'ai_research' is the normal path (a
# PlaceQuestion, generated from category coverage gaps, gets answered and
# verified); 'seed' mirrors PlaceQuestion.source's existing convention for
# human-curated content that never went through a question at all.
CATEGORY_KNOWLEDGE_SOURCES = ("ai_research", "seed")


class CategoryKnowledge(Base):
    """What TrailMind currently knows and trusts about ONE Location + ONE
    assigned category -- the PRIMARY knowledge system (Location -> Categories
    -> CategoryKnowledge -> Questions -> Verification -> Fresh/Stale/Missing).

    Deliberately NOT keyed on a bare category_id: it belongs to one specific
    LocationCategoryAssignment (the (location, category, relevance) tuple),
    never to a category in the abstract or to more than one category at once
    -- a fact relevant to two categories becomes two separate rows, so one
    verification event can never inflate two categories' coverage at once
    (see the architecture doc's Part 3.2 for why this is deliberate).

    ROW LIFECYCLE, NOT JUST COLUMN VALUES:
      - Created the moment a guide's answer produces an Observation for this
        knowledge concern (see app/services/extractions.py's category-
        knowledge branch) -- `last_verified_at` starts NULL ("known about,
        not yet trusted").
      - `last_verified_at` is set ONLY when that Observation's moderation
        (app/services/observation_moderation.py::approve/change_decision)
        actually approves it -- never by question generation, never by a raw
        answer, never by Perplexity research. This is the one, single trigger
        for "a trusted guide verified this."
      - A category only counts a row as covering it once last_verified_at is
        non-null -- an unverified/pending row does NOT count as coverage, so
        two guides answering the same missing-knowledge question in quick
        succession before either is moderated do not silently double-cover a
        category from unverified content.

    FRESHNESS IS COMPUTED, NEVER STORED: stale_at = last_verified_at +
    freshness_duration_hours; fresh/stale is `now` compared against that,
    always derived (see services/category_knowledge.py). Storing a `status`
    column here would create exactly the "inconsistent stored state" problem
    this design is built to avoid -- nothing sweeps this table on a schedule.

    `freshness_duration_hours` is a SNAPSHOT, taken at creation from
    category_knowledge_policy.py's volatility->hours mapping -- never re-read
    live, so a later change to that mapping (or an admin override on a
    different row) never silently reinterprets an already-computed stale_at.
    """

    __tablename__ = "category_knowledge"
    __table_args__ = (
        # "What do we know about this Location, across all its categories" --
        # the coverage-rollup access pattern (services/category_knowledge.py).
        Index("ix_category_knowledge_location_id", "location_id"),
        # "What do we know about this Location's THIS category" -- the
        # per-category coverage/state lookup.
        Index(
            "ix_category_knowledge_assignment_active",
            "category_assignment_id",
            "active",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Denormalized from category_assignment_id, purely for the location-wide
    # coverage-rollup query -- same denormalization convention
    # LocationCategoryAssignment.kind already uses off LocationCategory.
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="CASCADE"), nullable=False
    )
    # RESTRICT: an assignment can't be deleted out from under standing
    # knowledge without an explicit decision -- retire the assignment's
    # `active` flag instead, mirroring location_categories' own RESTRICT.
    category_assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("location_category_assignments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    knowledge_text: Mapped[str] = mapped_column(Text, nullable=False)
    volatility: Mapped[str] = mapped_column(String(20), nullable=False)
    freshness_duration_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    # NULL until a guide's verification of this exact concern clears
    # moderation -- see the class docstring. Never set by question
    # generation, a raw answer, extraction, or Perplexity research.
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # The PlaceQuestion that produced this row (first-ask) or most recently
    # re-verified it. Nullable only for 'seed' rows that never went through a
    # question at all -- mirrors PlaceQuestion.source_finding_id's own
    # SET NULL convention: a knowledge item must outlive the question that
    # first asked about it.
    source_question_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("place_questions.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Which Perplexity finding (if any) originally surfaced this concern --
    # reuses the EXISTING findings table, not a new one.
    source_finding_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("place_research_findings.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Set when a LATER verification contradicts (not merely reconfirms) this
    # row -- e.g. a guide reports the cafe no longer serves what this row
    # says it's known for. The old row is deactivated and left exactly as it
    # was (full history preserved via Observation); a new row is created with
    # the corrected text. Self-referential, SET NULL so a superseding row's
    # own later removal never cascades back onto the row it superseded.
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("category_knowledge.id", ondelete="SET NULL"),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ai_research")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
