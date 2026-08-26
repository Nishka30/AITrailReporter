from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.knowledge_type_config import KnowledgeTypeConfig


def get_active_knowledge_types(db: Session) -> list[KnowledgeTypeConfig]:
    """The only knowledge types an LLM extraction is ever allowed to use (Step 9).
    Database configuration is the source of truth -- the caller must never fall
    back to a hardcoded list if this comes back empty."""
    stmt = (
        select(KnowledgeTypeConfig)
        .where(KnowledgeTypeConfig.active.is_(True))
        .order_by(KnowledgeTypeConfig.knowledge_type)
    )
    return list(db.execute(stmt).scalars().all())


def get_active_knowledge_type_by_name(db: Session, knowledge_type: str) -> KnowledgeTypeConfig | None:
    """Used by Step 12 question generation to resolve a caller-supplied
    knowledge_type string before doing anything else -- an inactive or unknown
    type is rejected immediately, never silently treated as a valid gap
    target."""
    stmt = select(KnowledgeTypeConfig).where(
        KnowledgeTypeConfig.knowledge_type == knowledge_type,
        KnowledgeTypeConfig.active.is_(True),
    )
    return db.execute(stmt).scalar_one_or_none()
