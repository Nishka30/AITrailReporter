import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Route(Base):
    """A named, ordered sequence of existing Locations -- a trek, a driving
    loop, any journey worth showing as a strip of stops. Genuinely reusable:
    nothing about this model or its RouteStop rows is specific to any one
    route. The Everest Base Camp trek is the first row, seeded by
    scripts/seed_routes.py -- not a special case baked into the schema.
    """

    __tablename__ = "routes"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_routes_slug"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(150), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class RouteStop(Base):
    """One Location's position on one Route.

    WHY NO GEOGRAPHY COLUMN OF ITS OWN: a stop's position IS its Location's
    own `geog`, reached via `location_id` -- duplicating coordinates here
    would let a stop silently drift from the place it is supposed to be. Same
    "reference, never re-store" reasoning CuratedHub gives for pointing at a
    Location rather than owning its own place data.

    `ondelete=CASCADE` on both FKs: a Route or a Location are not expected to
    be deleted in ordinary operation, and if either is, a stop describing the
    relationship between them has nothing left to mean.
    """

    __tablename__ = "route_stops"
    __table_args__ = (
        # A Location appears at most once on a given Route.
        UniqueConstraint("route_id", "location_id", name="uq_route_stops_route_location"),
        # No two stops on the same Route share an ordering position.
        UniqueConstraint("route_id", "sequence_order", name="uq_route_stops_route_sequence_order"),
        # Supports "this route's stops, in order" -- the only read pattern
        # get_public_route_for_location needs once it has a route_id.
        Index("ix_route_stops_route_id_sequence_order", "route_id", "sequence_order"),
        # Supports "does this Location belong to a route, and which one" --
        # checked on every public Location detail read.
        Index("ix_route_stops_location_id", "location_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    route_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("routes.id", ondelete="CASCADE"), nullable=False
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="CASCADE"), nullable=False
    )
    sequence_order: Mapped[int] = mapped_column(Integer, nullable=False)
    # Display override ("Overnight stop", "Lunch halt") -- optional; the
    # frontend falls back to the Location's own name when absent.
    stop_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Descriptive display metadata only -- never read by any freshness/status
    # logic, purely for the route strip's own card content.
    elevation_meters: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
