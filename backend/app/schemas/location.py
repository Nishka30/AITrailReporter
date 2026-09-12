from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class LocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    latitude: float
    longitude: float
    created_at: datetime
    updated_at: datetime


class NearbyLocationResult(BaseModel):
    id: UUID
    name: str
    description: str | None
    latitude: float
    longitude: float
    distance_meters: float


class PlaceCandidate(BaseModel):
    """One place the guide could choose to contribute to, from
    GET /api/v1/locations/candidates.

    Every field comes off a real, shared `Location` row -- this is a VIEW of
    the existing table, never a parallel place model. `id` is therefore the
    same Location id every other endpoint uses, which is what makes "two
    guides picking the same place contribute to the same record" true by
    construction rather than by convention.
    """

    id: UUID
    name: str
    distance_meters: float
    latitude: float
    longitude: float
    # TrailMind's own taxonomy (see services/places/categories.py), not
    # Google's raw type -- null when the place was created before
    # classification existed or classified as nothing in particular.
    category: str | None = None
    subcategory: str | None = None
    # Google's own type string, kept so the app can refine presentation later
    # without a new backend round trip.
    place_kind: str | None = None
    # Present only for places Google identified. Null for hand-created rows
    # and for anything discovered by the retired OSM pipeline.
    external_place_id: str | None = None
    provider: str | None = None
    formatted_address: str | None = None
    # True for a reverse-geocoded AREA (a neighbourhood/village the coordinate
    # falls inside) rather than a specific POI. The app uses this to label and
    # order the broadest option honestly -- see services/place_candidates.py.
    is_area: bool = False


class PlaceCandidateResponse(BaseModel):
    latitude: float
    longitude: float
    radius_meters: float
    candidates: list[PlaceCandidate]
