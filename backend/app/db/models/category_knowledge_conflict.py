import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

CONFLICT_STATUSES = ("open", "resolved")
CONFLICT_RESOLUTIONS = ("confirmed", "superseded", "dismissed")


class CategoryKnowledgeConflict(Base):
    """Recorded whenever a re-verification's relationship to an already-
    verified CategoryKnowledge item could not be confidently classified as
    CONFIRMS or CONTRADICTS (see app/services/knowledge_relation.py) -- the
    explicit "do NOT silently choose one interpretation" resolution path the
    knowledge-architecture hardening pass requires.

    Created the moment moderation approves the evidencing Observation (the
    SAME call site as category_knowledge.mark_verified/supersede_knowledge_item
    -- see observation_moderation.py::_maybe_verify_category_knowledge), never
    before: an unmoderated answer never even reaches this judgement. The
    existing CategoryKnowledge row is left completely untouched while a
    conflict is open -- this table is read-only with respect to trust state
    until an admin resolves it (see category_knowledge.py::resolve_conflict).
    """

    __tablename__ = "category_knowledge_conflicts"
    __table_args__ = (
        Index("ix_category_knowledge_conflicts_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # The existing, trusted item the new evidence could not be confidently
    # related to. RESTRICT: a conflict record must survive until resolved.
    category_knowledge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("category_knowledge.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # The Observation whose approval surfaced this ambiguity. UNIQUE: an
    # observation can be approved into ambiguity at most once.
    observation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("observations.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    new_answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="open")
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Populated only when an admin resolves this as 'superseded' -- the new
    # CategoryKnowledge row created at resolution time. SET NULL so a later
    # removal of that row can never cascade back into destroying this audit
    # record (mirrors CategoryKnowledge.superseded_by_id's own convention).
    resolved_knowledge_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("category_knowledge.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
