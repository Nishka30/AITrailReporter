import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KnowledgeTypeConfig(Base):
    """Per-knowledge-type freshness/relevance policy. There is no global freshness window —
    every knowledge type (weather, trail_condition, snow_ice, ...) configures its own here."""

    __tablename__ = "knowledge_type_config"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    knowledge_type: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    freshness_window_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    aging_threshold_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    geographic_relevance_radius_meters: Mapped[int] = mapped_column(Integer, nullable=False)
    default_priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    safety_critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
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
