import uuid
from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import DateTime, ForeignKey, Index, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Observation(Base):
    """A structured fact, eventually extracted from a submission (e.g. trail_condition=muddy)."""

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
    knowledge_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_type_config.id", ondelete="RESTRICT"),
        nullable=False,
    )
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    geog = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=True)
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
