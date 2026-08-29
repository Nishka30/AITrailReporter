import uuid
from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import DateTime, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# How a Location came to exist.
#   'manual'     -- created by a person or a seed migration. The default, and
#                   the only kind that existed before POI discovery.
#   'discovered' -- created by app/services/poi_discovery.py from web research
#                   about what is actually near a guide's coordinates.
#
# Recorded because the two carry different trust: a manual row was vouched for
# by a human, a discovered one is only as good as its `source_urls`. Keeping
# them distinguishable means a discovered row can always be reviewed, audited
# or removed en masse without touching curated data.
LOCATION_SOURCES = ("manual", "discovered")


class Location(Base):
    """A known, named geographic place (e.g. a village, viewpoint, junction).

    Locations are the anchor of the entire place-specific experience: a guide's
    raw GPS only becomes "you're at Hillary Bridge" because a Location row sits
    within `geographic_context_radius_meters` of them (see
    app/services/geographic_context.py). With an empty table, every downstream
    feature -- place research, "you're here" invitations, place-scoped rewards --
    silently degrades to generic behaviour, because there is nothing to be
    specific ABOUT.

    That is why POI discovery exists (app/services/poi_discovery.py): it fills
    this table from real web research so the system can be specific in places
    nobody has curated by hand.
    """

    __tablename__ = "locations"
    __table_args__ = (
        # Supports "has this discovery cell already produced places?" and
        # bulk review/cleanup of one discovery run.
        Index("ix_locations_discovery_cell_key", "discovery_cell_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    geog = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=False)
    # One of LOCATION_SOURCES. server_default 'manual' so every pre-existing
    # row keeps its true provenance without a guessing backfill.
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="manual")
    # What kind of place this is ("bridge", "cafe", "viewpoint", "monastery"),
    # as established by research. Free text rather than an enum: the whole point
    # of discovery is finding place types nobody enumerated in advance. Null for
    # manually created rows, which never had to declare one.
    place_kind: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Where this place is, in words a search engine understands: "Koramangala,
    # Bengaluru, India". Resolved once by reverse geocoding and then reused
    # forever (see poi_discovery_research/osm_provider.reverse_geocode_locality).
    #
    # NOT decoration. Web research for a place named "Ganesh Temple" returns
    # noise from every city on earth; the same research for "Ganesh Temple in
    # Koramangala, Bengaluru" returns the right building. This column is the
    # difference between those two outcomes, which is why it is stored on the
    # Location rather than recomputed per research run.
    locality: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Real citations backing a discovered place's existence, name and position.
    # A discovered row is never written without at least one (see
    # app/services/poi_discovery.py) -- an unsourced "landmark" is exactly the
    # fabrication this system must not produce.
    source_urls: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Which discovery grid cell produced this row. Lets one run be traced,
    # reviewed or reverted as a unit. Null for manually created rows.
    discovery_cell_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
