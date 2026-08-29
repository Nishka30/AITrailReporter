from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas.location import LocationCreate, LocationRead, NearbyLocationResult
from app.services import locations as location_service
from app.services import poi_discovery as poi_discovery_service

router = APIRouter(prefix="/api/v1/locations", tags=["locations"])


@router.post("", response_model=LocationRead, status_code=201)
def create_location(payload: LocationCreate, db: Session = Depends(get_db)):
    return location_service.create_location(db, payload)


# Registered before "/{location_id}" so the literal path "nearby" is matched first —
# otherwise it would be swallowed by the {location_id} route and fail UUID parsing.
@router.get("/nearby", response_model=list[NearbyLocationResult])
def get_nearby_locations(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    radius_meters: float = Query(gt=0, le=settings.nearby_search_max_radius_meters),
    db: Session = Depends(get_db),
):
    return location_service.find_nearby_locations(db, latitude, longitude, radius_meters)


@router.post("/discover", response_model=list[NearbyLocationResult])
def discover_locations(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    force: bool = Query(
        default=False,
        description=(
            "Re-discover even if this grid cell was researched recently. Costs "
            "real web searches -- use deliberately."
        ),
    ),
    db: Session = Depends(get_db),
):
    """Finds and stores the REAL named places around a coordinate.

    Synchronous and slow BY DESIGN -- this is the operator/seeding entry point,
    where waiting for the answer is the whole purpose. The mobile app never
    calls it: guide-facing discovery is scheduled in the background from
    GET /guides/{id}/popular-questions so nothing there ever blocks.

    Returns the known places near this coordinate afterwards, which is the
    honest answer to "what did that achieve" -- including when the answer is
    'nothing new', because discovery found nothing it could source.
    """
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=503, detail="Place discovery is not configured on the server."
        )

    poi_discovery_service.ensure_discovered(db, latitude, longitude, force=force)
    return location_service.find_nearby_locations(
        db, latitude, longitude, settings.poi_discovery_accept_radius_meters
    )


@router.get("/{location_id}", response_model=LocationRead)
def get_location(location_id: UUID, db: Session = Depends(get_db)):
    location = location_service.get_location(db, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return location
