import uuid
from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import DateTime, Float, ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GuideLocation(Base):
    """Historical GPS events for a guide. Rows are append-only — never overwritten."""

    __tablename__ = "guide_locations"
    __table_args__ = (
        Index("ix_guide_locations_guide_id_recorded_at", "guide_id", "recorded_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    guide_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("guides.id", ondelete="CASCADE"), nullable=False
    )
    # Stable client-generated id (the mobile app's local UUID) used to make location
    # ingestion idempotent, on the same principle as Guide.client_guide_id and
    # Submission.client_submission_id. Nullable so callers that don't supply one
    # (no idempotency requested) aren't blocked; unique whenever it is supplied.
    client_location_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )
    latitude: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    geog = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=False)
    accuracy_meters: Mapped[float | None] = mapped_column(Float, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
