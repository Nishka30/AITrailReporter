import uuid as uuid_module
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GuideLocationCreate(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_meters: float | None = Field(default=None, gt=0)
    recorded_at: datetime
    # Stable client-generated id (e.g. a mobile app's local UUID). When supplied,
    # location ingestion is idempotent on this value: a repeat request with the same
    # client_location_id and matching data returns the already-stored location
    # instead of creating another.
    client_location_id: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("recorded_at")
    @classmethod
    def require_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("recorded_at must be timezone-aware")
        return value

    @field_validator("client_location_id")
    @classmethod
    def validate_client_location_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            uuid_module.UUID(value)
        except ValueError as exc:
            raise ValueError("client_location_id must be a valid UUID string") from exc
        return value


class GuideLocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    guide_id: UUID
    client_location_id: str | None
    latitude: float
    longitude: float
    accuracy_meters: float | None
    recorded_at: datetime
    received_at: datetime
    created_at: datetime


class NearbyGuideResult(BaseModel):
    guide_id: UUID
    name: str
    phone_number: str | None
    latitude: float
    longitude: float
    recorded_at: datetime
    distance_meters: float
