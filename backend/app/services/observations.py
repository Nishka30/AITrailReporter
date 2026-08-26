from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.knowledge_type_config import KnowledgeTypeConfig
from app.db.models.observation import Observation


def list_observations_for_submission(db: Session, submission_id: UUID) -> list[tuple[Observation, str]]:
    """Every persisted observation for a submission, paired with its
    human-readable knowledge_type string via an explicit join (Observation only
    stores knowledge_type_id -- see app/schemas/observation.py for why)."""
    stmt = (
        select(Observation, KnowledgeTypeConfig.knowledge_type)
        .join(KnowledgeTypeConfig, KnowledgeTypeConfig.id == Observation.knowledge_type_id)
        .where(Observation.submission_id == submission_id)
        .order_by(Observation.created_at)
    )
    return [(row[0], row[1]) for row in db.execute(stmt).all()]
