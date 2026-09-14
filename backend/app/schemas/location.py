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
    # For a curated seed row (provider='seed' -- see services/seed_import.py)
    # only: how much the curator trusted this coordinate ("High"/"Medium"/
    # "Low"), and what kind of point it represents ("Venue point" vs "Point /
    # area anchor"). Preserved verbatim, null for every other row. Not
    # currently rendered by the app -- confidence already affects backend
    # ranking (a Low-confidence candidate sorts slightly behind an equally-
    # distant one we're more sure of); these are exposed for the same reason
    # every other provenance field on this schema is, so a consumer can
    # inspect what's known about a candidate without a second round trip.
    coordinate_confidence: str | None = None
    coordinate_type: str | None = None
    # True for a reverse-geocoded AREA (a neighbourhood/village the coordinate
    # falls inside) rather than a specific POI. The app uses this to label and
    # order the broadest option honestly -- see services/place_candidates.py.
    is_area: bool = False


class LocationCategoryRead(BaseModel):
    """One category assigned to a Location, from
    GET /api/v1/locations/{id}/categories.

    A Location has several of these at once -- a bazaar is Shopping and Food
    and Local Life -- which is the whole point of the table behind it. See
    app/services/places/category_catalog.py.
    """

    # 'theme' (what the place is ABOUT) or 'place_type' (what it IS).
    kind: str
    # Stable machine name -- match on this, never on display_name.
    slug: str
    display_name: str
    # 0-100, how much this category matters FOR THIS PLACE. What a future
    # live-information view would rank by.
    relevance: int
    # 0-1, how trustworthy the evidence behind the classification was.
    # Distinct from relevance on purpose: "definitely a cafe, and that barely
    # matters here" and "possibly a viewpoint, and if so it is the whole
    # point" are different statements.
    confidence: float
    # True for the single most-defining category of each kind. The primary
    # pair mirrors the legacy (category, subcategory) columns.
    is_primary: bool
    # How this was established: google_type / seed_type / name_rule /
    # rule_implied / ai / manual.
    source: str


class LocationCategoriesResponse(BaseModel):
    location_id: UUID
    location_name: str
    categories: list[LocationCategoryRead]


class CategorisedLocationRead(BaseModel):
    """A place found BY category, from GET /api/v1/locations/by-category."""

    id: UUID
    name: str
    latitude: float
    longitude: float
    # How much the requested category defines THIS place, so results can be
    # ranked by fit and not merely listed.
    relevance: int
    confidence: float
    # Null when the query supplied no coordinate to measure from.
    distance_meters: float | None = None


class PlaceCandidateResponse(BaseModel):
    latitude: float
    longitude: float
    radius_meters: float
    candidates: list[PlaceCandidate]
