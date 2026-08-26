from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas.location import LocationCreate, LocationRead, NearbyLocationResult
from app.services import locations as location_service

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


@router.get("/{location_id}", response_model=LocationRead)
def get_location(location_id: UUID, db: Session = Depends(get_db)):
    location = location_service.get_location(db, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return location
