import uuid
from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import DateTime, Index, Numeric, String, Text, UniqueConstraint, func
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
        # An exact identity match is the strongest dedup signal there is: if
        # this provider has already told us about this exact external id, it
        # is the same place, full stop. Two columns (not just
        # external_place_id alone) because the same raw id string could in
        # principle exist under two different providers. Postgres's standard
        # multi-column UNIQUE semantics mean any-NULL rows (every manual
        # Location, and every discovered one predating this column) never
        # collide with each other or with populated rows.
        UniqueConstraint(
            "provider", "external_place_id", name="uq_locations_provider_external_place_id"
        ),
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
    # forever (see app/services/places/google_provider.py's
    # reverse_geocode_locality).
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
    # Which place-identification backend supplied this row: "openstreetmap"
    # (legacy, backfilled onto pre-Google discovered rows), "google", "seed"
    # (a curated spreadsheet row -- see services/seed_import.py), or null for
    # a hand-created manual row with no such backend at all. A DIFFERENT
    # thing from PoiDiscovery.provider, which records which backend a whole
    # discovery RUN used -- this one records which backend identified THIS
    # SPECIFIC place, since a place found via user-selected search or seed
    # import never goes through a PoiDiscovery row at all.
    provider: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # The provider's own stable id for this place (e.g. a Google Place ID).
    # Paired with `provider` in a UNIQUE constraint below -- this is what lets
    # "has this exact place already been discovered?" be answered exactly,
    # not just approximately by distance.
    external_place_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Google's own primary classification for this place (e.g. "cafe",
    # "hindu_temple"). Preserved verbatim even though `category`/`subcategory`
    # below are TrailMind's own vocabulary derived from it -- so
    # classification can be improved later without re-fetching anything.
    #
    # `provider` also holds "seed" for a row created by
    # services/seed_import.py from curated spreadsheet data (see that
    # module's docstring) -- a THIRD kind of place identification alongside
    # "openstreetmap"/"google", distinguished the same way those two already
    # are. `google_primary_type` stays genuinely Google-only for such rows
    # (null); the curated data's own free-text type/category lives in
    # `place_kind` below instead, exactly like a discovered row's raw type
    # does.
    google_primary_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    google_types: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # TrailMind's OWN taxonomy (see app/services/places/categories.py),
    # deterministically derived from google_primary_type/google_types/name.
    # Never left null for a discovered row without a confident mapping --
    # "Other"/"Other" is the honest fallback, not a missing value.
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    subcategory: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Google's formatted address string, kept for admin display -- NOT used
    # as the locality passed into place research (see `locality` above, which
    # is deliberately just neighbourhood+city, not a full postal address).
    #
    # For a `provider='seed'` row this instead holds the curator's own
    # "Area / street" text (e.g. "Tridevi Sadak") -- not Google's, but the
    # same admin-display role: a short, human-written location fragment, not
    # the neighbourhood+city string `locality` needs for research queries.
    formatted_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # How much the SUPPLIER of this coordinate trusted it, verbatim from
    # curated seed data ("High"/"Medium"/"Low" -- see
    # services/seed_import.py). Null for every row that isn't seed-sourced:
    # Google-discovered coordinates carry no such self-reported confidence,
    # and a manually placed pin is trusted by construction. Preserved as
    # supplied rather than collapsed into a score, so a human reviewing this
    # data later sees exactly what the curator wrote. `services/
    # place_candidates.py` reads this to rank a Low-confidence seed place
    # slightly below an equally-distant place we are more sure of -- see
    # that module's `_CONFIDENCE_PENALTY_METERS` for exactly how.
    coordinate_confidence: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # What KIND of point the coordinate represents, verbatim from curated
    # seed data ("Venue point" -- a specific doorway/counter -- vs "Point /
    # area anchor" -- a representative point for a broader square, complex or
    # bazaar that has no single front door). Descriptive metadata only, kept
    # for admin display and future refinement; nothing currently branches on
    # its value. Null for every non-seed row, and for seed rows whose source
    # sheet didn't supply this column at all (the Lukla sheet has no such
    # column, unlike Thamel's).
    coordinate_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
