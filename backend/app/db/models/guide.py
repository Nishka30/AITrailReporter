import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Short codes for the tour-operator brands a guide may be affiliated with.
# Display names are presentation-only and intentionally not stored:
#   BCT -> BaseCampTours
#   HW  -> HimalayanWonders
#   TH  -> TrekkingHero
#   PH  -> PatagoniaHero
# The only four supported values today -- see schemas/guide.py's validator,
# which is what actually keeps arbitrary strings out of the column below
# (Postgres JSONB itself has no way to constrain the contents of a list).
GUIDE_BRANDS = ("BCT", "HW", "TH", "PH")


class Guide(Base):
    __tablename__ = "guides"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Stable client-generated id (e.g. a mobile app's local UUID) used to make guide
    # creation idempotent. Nullable so guides created through other future paths
    # aren't forced to have one; a unique index enforces "same client id -> same
    # guide" whenever it is supplied.
    client_guide_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )
    # Exactly one of GUIDE_BRANDS, e.g. "BCT" -- a guide belongs to a single
    # brand, so this is a plain scalar column rather than a list. Null for a
    # guide created before this field existed, or any guide with none
    # recorded -- never defaulted or invented. See schemas.guide for the
    # validation that keeps this restricted to GUIDE_BRANDS.
    brand: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
