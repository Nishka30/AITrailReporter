"""Places browser: reuses the existing Location table and PostGIS
ST_DWithin/ST_Distance -- no client-side Haversine, no second geodata store."""

from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.location import Location
from app.db.models.observation import Observation
from app.db.models.observation_moderation import ObservationModeration
from app.schemas.admin import PlaceDetail, PlaceSummary
from app.services.admin_review import ReviewQueueFilters, list_review_queue


def list_places(db: Session) -> list[PlaceSummary]:
    """One row per Location, with nearby/pending/approved observation counts
    computed in a SINGLE query (not one query per place) via an outer join
    scoped by ST_DWithin, using the same "known place nearby" radius as
    app/services/geographic_context.py."""
    radius = settings.geographic_context_radius_meters
    stmt = (
        select(
            Location.id,
            Location.name,
            Location.latitude,
            Location.longitude,
            func.count(Observation.id).label("nearby_count"),
            func.coalesce(
                func.sum(case((ObservationModeration.status == "pending_review", 1), else_=0)), 0
            ).label("pending_count"),
            func.coalesce(
                func.sum(case((ObservationModeration.status == "approved", 1), else_=0)), 0
            ).label("approved_count"),
        )
        .outerjoin(
            Observation,
            (Observation.geog.isnot(None)) & (func.ST_DWithin(Observation.geog, Location.geog, radius)),
        )
        .outerjoin(ObservationModeration, ObservationModeration.observation_id == Observation.id)
        .group_by(Location.id, Location.name, Location.latitude, Location.longitude)
        .order_by(Location.name)
    )
    rows = db.execute(stmt).all()
    return [
        PlaceSummary(
            location_id=row.id,
            name=row.name,
            latitude=float(row.latitude),
            longitude=float(row.longitude),
            nearby_observation_count=row.nearby_count,
            pending_review_count=row.pending_count,
            approved_count=row.approved_count,
        )
        for row in rows
    ]


def get_place_detail(db: Session, location_id: UUID, limit: int = 25) -> PlaceDetail | None:
    location = db.get(Location, location_id)
    if location is None:
        return None

    result = list_review_queue(
        db, ReviewQueueFilters(place_id=location_id, sort="observed_at"), page=1, page_size=limit
    )
    return PlaceDetail(
        location_id=location.id,
        name=location.name,
        description=location.description,
        latitude=float(location.latitude),
        longitude=float(location.longitude),
        recent_observations=result.items,
    )
