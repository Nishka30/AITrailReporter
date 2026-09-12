from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas.location import (
    LocationCreate,
    LocationRead,
    NearbyLocationResult,
    PlaceCandidate,
    PlaceCandidateResponse,
)
from app.services import locations as location_service
from app.services import place_candidates as place_candidate_service
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


# Also registered before "/{location_id}", same reason as "/nearby" above.
@router.get("/candidates", response_model=PlaceCandidateResponse)
def get_place_candidates(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    limit: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
):
    """The places a guide at this coordinate could choose to contribute to.

    DISTINCT FROM "/nearby" ABOVE, which is a raw spatial read of the
    `locations` table at a caller-supplied radius. This one discovers places
    that are not known yet, filters out what a guide could not report on,
    removes duplicate representations of the same real-world place, and ranks
    what survives. "/nearby" stays exactly as it was for operator/API use.

    DISTINCT FROM the single place `/guides/{id}/context` reports, which
    answers "where is this guide?". A contribution is about a SUBJECT the
    guide chooses, and the nearest listed POI is frequently not it -- see the
    module docstring in services/place_candidates.py.

    Returns the guide's own coordinates back alongside the list so the caller
    can show distances it did not compute itself, and never 404s: an empty
    `candidates` list is the honest answer mid-ocean or during a Google
    outage, not an error.
    """
    limit = min(limit or settings.place_candidate_limit, settings.place_candidate_max_limit)
    candidates = place_candidate_service.find_place_candidates(
        db, latitude, longitude, limit=limit
    )
    return PlaceCandidateResponse(
        latitude=latitude,
        longitude=longitude,
        radius_meters=settings.place_candidate_radius_meters,
        candidates=[PlaceCandidate(**vars(candidate)) for candidate in candidates],
    )


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
