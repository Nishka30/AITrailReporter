import uuid as uuid_module
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.db.models.guide import GUIDE_BRANDS


def _validate_brand(value: str | None) -> str | None:
    """Keeps `brand` restricted to GUIDE_BRANDS, shared by GuideCreate and
    GuideUpdate so the two can never drift.

    None means "no brand information supplied" and is always allowed -- this
    is what keeps existing guides, and any caller that predates this field
    (e.g. internal test fixtures that create a Guide with only a name), safe
    and unchanged.
    """
    if value is None:
        return None
    if value not in GUIDE_BRANDS:
        raise ValueError(
            f"Unknown brand code: {value}. Must be one of {', '.join(GUIDE_BRANDS)}."
        )
    return value


class GuideCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    phone_number: str | None = Field(default=None, max_length=32)
    # Stable client-generated id (e.g. a mobile app's local UUID). When supplied,
    # guide creation is idempotent on this value: a repeat request with the same
    # client_guide_id returns the already-created guide instead of making another.
    client_guide_id: str | None = Field(default=None, min_length=1, max_length=255)
    # One of GUIDE_BRANDS (e.g. "BCT"). Optional at the schema level -- see
    # _validate_brand's docstring for why None must stay accepted here -- but
    # the mobile Setup screen always sends one, since its own UI requires a
    # brand to be selected before saving.
    brand: str | None = Field(default=None)

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

    @field_validator("brand")
    @classmethod
    def validate_brand(cls, value: str | None) -> str | None:
        return _validate_brand(value)


class GuideUpdate(BaseModel):
    """Editable identity fields for an existing guide (Step 17: the mobile
    Profile screen).

    Carries name, phone_number, and brand — the editable fields the Guide
    model has. The Profile screen's "About you" text and profile photo are
    NOT here and are never sent to the server: they are personal metadata
    with no operational use in this system, and the privacy boundary is that
    profile metadata is not field knowledge (see backend/README.md). Adding
    them would mean storing and securing personal data the backend has no
    reason to hold.

    All three fields are optional so a caller can update one without
    restating the others; a request that sets none of them is rejected rather
    than silently doing nothing. phone_number and brand are explicitly
    nullable — passing null CLEARS them, which is why `model_fields_set`
    distinguishes "not mentioned" from "set to null".
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    phone_number: str | None = Field(default=None, max_length=32)
    brand: str | None = Field(default=None)

    @field_validator("brand")
    @classmethod
    def validate_brand(cls, value: str | None) -> str | None:
        return _validate_brand(value)

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "GuideUpdate":
        fields_set = self.model_fields_set
        if (
            self.name is None
            and "phone_number" not in fields_set
            and "brand" not in fields_set
        ):
            raise ValueError("At least one of 'name', 'phone_number', or 'brand' must be supplied")
        return self


class GuideRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    phone_number: str | None
    client_guide_id: str | None
    brand: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
