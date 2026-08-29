import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# An EIGHTH independent state machine (see place_question.py's comment for the
# previous seven). This one answers: "have we looked up what real places exist
# around this patch of the map, and did it work?"
#
# Structurally identical to PlaceQuestionResearch on purpose -- same
# claim/attempt/retry shape, same honest 'failed' state, same "only a
# SUCCESSFUL run moves the freshness timestamp" rule.
POI_DISCOVERY_STATUSES = ("pending", "processing", "completed", "failed")


class PoiDiscovery(Base):
    """Tracks the web-research lifecycle for ONE grid cell of the map.

    WHY A CELL AND NOT A POINT: a guide's GPS moves constantly, by metres, while
    they stand still. Keyed on raw coordinates, every jitter would look like a
    brand-new place to research and this table would grow without bound while
    re-paying for the same web searches. Keyed on a rounded cell (see
    app/services/poi_discovery.py:cell_key_for), an entire neighbourhood is
    researched once and every guide who walks through it afterwards is served
    from what that one run found.

    WHY IT IS NOT KEYED ON A Location: the whole point is that no Location
    exists here yet -- that is the problem being solved. Discovery runs against
    empty map, and its OUTPUT is Location rows.
    """

    __tablename__ = "poi_discovery"
    __table_args__ = (
        # Mirrors ix_place_question_research_status: supports finding runs
        # stuck processing or repeatedly failing.
        Index("ix_poi_discovery_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # The rounded grid cell this run covers, e.g. "12.93,77.63". UNIQUE, so two
    # guides in the same neighbourhood can never start duplicate runs -- the
    # constraint is the real guarantee, not an application check.
    cell_key: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    # The coordinate actually searched: the cell's centre, not the guide's exact
    # position. Recorded so a run is reproducible and so nothing here doubles as
    # a store of where a specific person was standing.
    center_latitude: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    center_longitude: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="anthropic")
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # How many Locations the last successful run actually created. Zero is a
    # legitimate, honest outcome -- plenty of the world genuinely has no
    # documented named places -- and is recorded rather than treated as failure.
    discovered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # When the last SUCCESSFUL run completed. Distinct from completed_at, which
    # also moves on failure, so a string of failures can never masquerade as
    # fresh coverage and suppress future attempts.
    discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
