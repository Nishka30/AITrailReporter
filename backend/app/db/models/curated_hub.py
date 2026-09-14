import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Default hub eligibility radius (metres). Chosen for the Thamel/Lukla launch
# data specifically, not a generic default meant to fit every future hub:
# both curated point-sets span well under this (Thamel's 49 points spread at
# most ~1.1km from their own centroid, Lukla's 15 at most ~0.5km -- see the
# seed importer's own validation output), so 2km comfortably covers every
# curated place in each hub with headroom, without being so wide that a guide
# on the far side of Kathmandu would be told they're "near Thamel."
DEFAULT_HUB_RADIUS_METERS = 2_000


class CuratedHub(Base):
    """Marks a Location as a curated seed-question HUB, and how far its
    eligibility radius reaches.

    WHY A SEPARATE TABLE RATHER THAN TWO COLUMNS ON `locations`: being a hub
    is a rare, deliberately curated property -- at launch exactly two rows
    out of however many thousand Locations exist -- not a trait most
    Locations have an opinion about. Bolting `is_hub`/`hub_radius_meters`
    onto the generic Location model would mean every other Location in the
    system carries two always-null columns for a concept that applies to a
    handful of rows, the same "separate lifecycle -> separate entity"
    reasoning `place_question.py` gives for keeping PlaceQuestion out of
    `questions`. It also keeps "which places are hubs" independently
    auditable and trivially extensible (a third hub is one INSERT, not a
    migration) without ever touching the Location table itself.

    `location_id` points at a REAL, already-resolved Location -- for the
    Thamel/Lukla launch data this is literally the same Google-sourced Area
    Location the existing reverse-geocode mechanism already produces for
    "what neighbourhood is this coordinate in" (see
    services/poi_discovery.py's maybe_resolve_area_place). A hub is not a
    parallel place concept; it is an ordinary Location that has additionally
    been curated as a seed-question anchor.

    Eligibility itself (is some OTHER Location within `radius_meters` of this
    hub's own coordinates?) is computed on read, via PostGIS, in
    services/seed_questions.py -- never cached or denormalized here.
    """

    __tablename__ = "curated_hubs"
    __table_args__ = (
        # One hub configuration per Location -- "is this a hub" is a
        # yes/no-with-a-radius fact about a place, not something that could
        # sensibly have two different answers.
        UniqueConstraint("location_id", name="uq_curated_hubs_location_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="CASCADE"), nullable=False
    )
    radius_meters: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_HUB_RADIUS_METERS
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
