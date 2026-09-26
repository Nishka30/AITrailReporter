import uuid
from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Observation(Base):
    """A structured fact, eventually extracted from a submission (e.g. trail_condition=muddy).

    THE SHARED VERIFICATION LEDGER for BOTH knowledge systems -- not
    KnowledgeTypeConfig's private table. Exactly one of knowledge_type_id /
    category_knowledge_id is populated on any given row (never both, never
    neither -- see the CHECK constraint below):
      - knowledge_type_id: a hazard/coordinate-based observation (the
        EXCEPTION system -- weather, trail_condition, snow_ice, obstruction).
      - category_knowledge_id: a Location+category verification event (the
        PRIMARY system). Moderation approving THIS observation is the one
        trigger that sets CategoryKnowledge.last_verified_at (see
        app/services/observation_moderation.py).
    """

    __tablename__ = "observations"
    __table_args__ = (
        # Supports the Step 10 knowledge-state query's exact access pattern:
        # WHERE knowledge_type_id = ? ORDER BY observed_at DESC LIMIT 1 (run once
        # per active knowledge type on every evaluation). Ascending column order
        # despite the DESC query, mirroring ix_guide_locations_guide_id_recorded_at
        # -- Postgres serves ORDER BY ... DESC fine via a backward index scan.
        # There was previously no index on knowledge_type_id at all (Postgres does
        # not auto-index foreign key columns); the existing GiST index on `geog`
        # (auto-created by GeoAlchemy2) already covers the ST_DWithin side.
        Index("ix_observations_knowledge_type_id_observed_at", "knowledge_type_id", "observed_at"),
        Index("ix_observations_category_knowledge_id", "category_knowledge_id"),
        # Every Observation serves exactly one of the two systems -- never
        # both (a row can't be simultaneously hazard AND category evidence)
        # and never neither (an Observation with no purpose at all would be
        # silent dead weight in the ledger).
        CheckConstraint(
            "(knowledge_type_id IS NOT NULL) <> (category_knowledge_id IS NOT NULL)",
            name="ck_observations_exactly_one_knowledge_target",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False
    )
    guide_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("guides.id", ondelete="CASCADE"), nullable=False
    )
    # Nullable as of the category-knowledge system: NOT NULL was the original
    # constraint back when KnowledgeTypeConfig was the only knowledge system --
    # now populated only for a hazard/coordinate-based observation. See the
    # CHECK constraint above for the "exactly one of the two" guarantee this
    # relies on instead.
    knowledge_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_type_config.id", ondelete="RESTRICT"),
        nullable=True,
    )
    # Populated only for a category-knowledge verification event (the PRIMARY
    # system). RESTRICT: a CategoryKnowledge row with verification history
    # attached can't be deleted out from under it -- deactivate instead.
    category_knowledge_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("category_knowledge.id", ondelete="RESTRICT"),
        nullable=True,
    )
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    geog = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=True)
    # Copied from the resolving Submission's location_source/location_evidence
    # at the moment extraction sets this row's coordinate (see
    # app/services/extractions.py:_resolve_observation_coordinates) --
    # PlaceQuestion-style docstring: WHY this is copied rather than joined back
    # to Submission is that a Submission's OWN location_source can be updated
    # later by best-effort historical inference, and an Observation must record
    # what was actually known about its coordinate AT THE TIME it was created,
    # not whatever the source row says today. Nullable for pre-existing rows
    # and for the (rare) coordinate-less observation.
    location_source: Mapped[str | None] = mapped_column(String(30), nullable=True)
    location_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    # Short grounding text from the source (Step 9) -- why the extractor produced
    # this observation. Nullable at the DB level for schema-migration safety only;
    # the extraction pipeline (app/services/extractions.py) always sets it.
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
