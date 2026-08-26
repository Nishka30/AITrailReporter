from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class NearestKnownPlace(BaseModel):
    id: UUID
    name: str
    distance_meters: float


class GeographicContext(BaseModel):
    latitude: float
    longitude: float
    nearest_known_place: NearestKnownPlace | None = None


class GuideContext(BaseModel):
    guide_id: UUID
    guide_name: str
    latitude: float
    longitude: float
    recorded_at: datetime
    accuracy_meters: float | None
    nearest_known_place: NearestKnownPlace | None = None
