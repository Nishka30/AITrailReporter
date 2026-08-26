from sqlalchemy.orm import Session

from app.core.config import settings
from app.schemas.geographic_context import GeographicContext, NearestKnownPlace
from app.services import locations as location_service


def resolve_geographic_context(
    db: Session, latitude: float, longitude: float
) -> GeographicContext:
    """Resolve a raw coordinate into geographic context: the nearest known place,
    if any known place falls within GEOGRAPHIC_CONTEXT_RADIUS_METERS. A place is
    only attached when it's actually within that radius — never "nearest regardless
    of distance"."""
    nearest = location_service.find_nearest_location(
        db, latitude, longitude, settings.geographic_context_radius_meters
    )
    nearest_known_place = (
        NearestKnownPlace(
            id=nearest["id"],
            name=nearest["name"],
            distance_meters=nearest["distance_meters"],
        )
        if nearest is not None
        else None
    )
    return GeographicContext(
        latitude=latitude,
        longitude=longitude,
        nearest_known_place=nearest_known_place,
    )
