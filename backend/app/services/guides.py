from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.guide import Guide
from app.schemas.guide import GuideCreate


def get_guide(db: Session, guide_id: UUID) -> Guide | None:
    return db.get(Guide, guide_id)


def get_guide_by_client_id(db: Session, client_guide_id: str) -> Guide | None:
    stmt = select(Guide).where(Guide.client_guide_id == client_guide_id)
    return db.execute(stmt).scalar_one_or_none()


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
