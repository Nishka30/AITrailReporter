from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.guide import Guide
from app.schemas.guide import GuideCreate, GuideUpdate


def get_guide(db: Session, guide_id: UUID) -> Guide | None:
    return db.get(Guide, guide_id)


def get_guide_by_client_id(db: Session, client_guide_id: str) -> Guide | None:
    stmt = select(Guide).where(Guide.client_guide_id == client_guide_id)
    return db.execute(stmt).scalar_one_or_none()


def update_guide(db: Session, guide_id: UUID, data: GuideUpdate) -> Guide | None:
    """Applies a partial identity update (Step 17: the mobile Profile screen).
    Returns the updated guide, or None if no such guide exists.

    Only fields the caller actually supplied are written — `model_fields_set`
    distinguishes "not mentioned" from "explicitly set to null", so clearing a
    phone number is possible while omitting it leaves the stored value alone.
    A field-by-field UPDATE like this needs no row lock and no idempotency key:
    it is last-write-wins on two independent scalar columns, with no read-then-
    write step that a concurrent update could interleave with. (Contrast the
    attach_*_to_submission functions, which DO lock, because they decide what to
    write based on what they just read.)

    Deliberately does NOT touch client_guide_id: that is the stable identity
    this guide is resolved by, and rewriting it would orphan every local record
    on the device that references it.
    """
    guide = db.get(Guide, guide_id)
    if guide is None:
        return None

    fields_set = data.model_fields_set
    if "name" in fields_set and data.name is not None:
        guide.name = data.name
    if "phone_number" in fields_set:
        guide.phone_number = data.phone_number

    db.commit()
    db.refresh(guide)
    return guide


def create_or_get_guide(db: Session, data: GuideCreate) -> tuple[Guide, bool]:
    """Create a guide, or return the existing one if client_guide_id was already used.

    Returns (guide, created) so the route can pick the right HTTP status. Race-safe:
    if two requests with the same client_guide_id commit concurrently, the loser's
    IntegrityError (from the DB unique constraint — not just an app-level check) is
    caught and resolved by re-fetching the winner's row.
    """
    if data.client_guide_id is not None:
        existing = get_guide_by_client_id(db, data.client_guide_id)
        if existing is not None:
            return existing, False

    guide = Guide(
        name=data.name,
        phone_number=data.phone_number,
        client_guide_id=data.client_guide_id,
    )
    db.add(guide)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if data.client_guide_id is not None:
            existing = get_guide_by_client_id(db, data.client_guide_id)
            if existing is not None:
                return existing, False
        raise
    db.refresh(guide)
    return guide, True
