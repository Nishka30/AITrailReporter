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
