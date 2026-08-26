import uuid as uuid_module
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GuideCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    phone_number: str | None = Field(default=None, max_length=32)
    # Stable client-generated id (e.g. a mobile app's local UUID). When supplied,
    # guide creation is idempotent on this value: a repeat request with the same
    # client_guide_id returns the already-created guide instead of making another.
    client_guide_id: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("client_guide_id")
    @classmethod
    def validate_client_guide_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            uuid_module.UUID(value)
        except ValueError as exc:
            raise ValueError("client_guide_id must be a valid UUID string") from exc
        return value


class GuideRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    phone_number: str | None
    client_guide_id: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
