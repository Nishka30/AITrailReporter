"""Admin read layer for CategoryKnowledgeConflict -- the explicit "UNCERTAIN"
resolution queue for Part 2E of the knowledge architecture hardening pass.
Joins CategoryKnowledgeConflict together with the CategoryKnowledge/Location/
LocationCategory rows it references -- the same "explicit joins in the
service layer, no ORM relationships" convention as admin_places.py. Actually
resolving a conflict is owned by app/services/category_knowledge.py's
resolve_conflict -- this module only ever reads.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.category_knowledge import CategoryKnowledge
from app.db.models.category_knowledge_conflict import CategoryKnowledgeConflict
from app.db.models.location import Location
from app.db.models.location_category import LocationCategory, LocationCategoryAssignment
from app.schemas.admin import CategoryKnowledgeConflictRead


def _query():
    return (
        select(CategoryKnowledgeConflict, CategoryKnowledge, Location, LocationCategory)
        .join(CategoryKnowledge, CategoryKnowledge.id == CategoryKnowledgeConflict.category_knowledge_id)
        .join(Location, Location.id == CategoryKnowledge.location_id)
        .join(
            LocationCategoryAssignment,
            LocationCategoryAssignment.id == CategoryKnowledge.category_assignment_id,
        )
        .join(LocationCategory, LocationCategory.id == LocationCategoryAssignment.category_id)
    )


def _to_read(conflict, knowledge, location, category) -> CategoryKnowledgeConflictRead:
    return CategoryKnowledgeConflictRead(
        id=conflict.id,
        category_knowledge_id=knowledge.id,
        observation_id=conflict.observation_id,
        location_id=location.id,
        location_name=location.name,
        category_display_name=category.display_name,
        existing_knowledge_text=knowledge.knowledge_text,
        existing_volatility=knowledge.volatility,
        new_answer_text=conflict.new_answer_text,
        status=conflict.status,
        resolution=conflict.resolution,
        resolved_by=conflict.resolved_by,
        resolved_at=conflict.resolved_at,
        created_at=conflict.created_at,
    )


def list_conflicts(db: Session, status: str | None = "open") -> list[CategoryKnowledgeConflictRead]:
    stmt = _query().order_by(CategoryKnowledgeConflict.created_at.desc())
    if status:
        stmt = stmt.where(CategoryKnowledgeConflict.status == status)
    rows = db.execute(stmt).all()
    return [_to_read(*row) for row in rows]


def get_conflict(db: Session, conflict_id: UUID) -> CategoryKnowledgeConflictRead | None:
    stmt = _query().where(CategoryKnowledgeConflict.id == conflict_id)
    row = db.execute(stmt).first()
    return _to_read(*row) if row is not None else None
