import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Which stage of the research plan produced a finding. See
# app/services/place_question_research/research_plan.py, which is the only
# thing that sets these.
PLACE_RESEARCH_TOPICS = ("interest", "current")


class PlaceResearchFinding(Base):
    """One answered web-research query about one Location.

    WHY THIS TABLE EXISTS: so the system can always answer "why did TrailMind
    ask me this?" with evidence rather than a shrug. A generated invitation
    points at the finding that justified it (place_questions.source_finding_id),
    and the finding records the exact query that was run, what came back, and
    which pages it came from. Without this, a question's grounding lives only
    inside a model call that has already ended, and "every place-specific claim
    has a traceable basis" becomes an assertion nobody can check.

    IT IS NOT A CACHE OF THE WEB. `summary` is capped
    (settings.place_research_max_summary_chars) and holds the research step's
    own condensed answer, not page contents. Findings are kept across refresh
    cycles rather than replaced, because a question answered a year ago must
    still be explainable today -- and they are small enough that a place
    accumulates a couple of rows per refresh window.

    TRUST BOUNDARY: `summary` is UNTRUSTED TEXT assembled from public web pages.
    It is scrubbed at the provider edge (app/services/research/sanitize.py)
    before it is ever stored, and anything that reads it back into a prompt must
    still wrap it as data rather than instructions. What a source says is
    evidence about what is worth checking -- never a fact this system asserts.
    That distinction is the whole point: the web says what people claim, the
    guide reports what is actually there.
    """

    __tablename__ = "place_research_findings"
    __table_args__ = (
        # Supports "what has been researched about this place, most recent
        # first" -- the provenance lookup, and the only access pattern.
        Index("ix_place_research_findings_location", "location_id", "retrieved_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="CASCADE"), nullable=False
    )
    # The research RUN this belongs to. Nullable and ON DELETE SET NULL: the
    # finding is the durable record, and it must outlive the lifecycle row that
    # happened to schedule it.
    research_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("place_question_research.id", ondelete="SET NULL"),
        nullable=True,
    )
    # One of PLACE_RESEARCH_TOPICS: which stage of the plan asked this.
    topic: Mapped[str] = mapped_column(String(30), nullable=False)
    # The exact text sent to the research provider. Stored verbatim so a poor
    # result can be diagnosed as a poor QUERY rather than guessed at.
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    # Real, openable citations. Parallel arrays rather than a joined table:
    # they are only ever read together, with the finding, for audit.
    source_urls: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    source_titles: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # When the web actually said this. Distinct from created_at: it is the age
    # of the EVIDENCE, which is what matters when judging whether a question
    # about current conditions is still worth asking.
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
