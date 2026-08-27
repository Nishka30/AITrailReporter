import uuid as uuid_module
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class GuideUpdate(BaseModel):
    """Editable identity fields for an existing guide (Step 17: the mobile
    Profile screen).

    Deliberately carries ONLY name and phone_number — the two fields the Guide
    model already has. The Profile screen's "About you" text and profile photo
    are NOT here and are never sent to the server: they are personal metadata
    with no operational use in this system, and the privacy boundary is that
    profile metadata is not field knowledge (see backend/README.md). Adding them
    would mean storing and securing personal data the backend has no reason to
    hold.

    Both fields are optional so a caller can update one without restating the
    other; a request that sets neither is rejected rather than silently doing
    nothing. phone_number is explicitly nullable — passing null CLEARS it, which
    is why `phone_number_set` distinguishes "not mentioned" from "set to null".
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    phone_number: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "GuideUpdate":
        if self.name is None and "phone_number" not in self.model_fields_set:
            raise ValueError("At least one of 'name' or 'phone_number' must be supplied")
        return self


class GuideRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    phone_number: str | None
    client_guide_id: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
