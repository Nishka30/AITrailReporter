"""Overview stats for the admin dashboard's landing page. Every field is a
direct COUNT() at request time -- never a fabricated or placeholder number,
per the admin dashboard spec's explicit requirement."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.guide import Guide
from app.db.models.knowledge_type_config import KnowledgeTypeConfig
from app.db.models.observation import Observation
from app.db.models.observation_moderation import ObservationModeration
from app.db.models.question import Question
from app.db.models.question_assignment import QuestionAssignment
from app.db.models.submission import Submission
from app.schemas.admin import AdminOverview


def _count(db: Session, stmt) -> int:
    return db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()


def get_overview(db: Session) -> AdminOverview:
    total_guides = _count(db, select(Guide.id))
    total_submissions = _count(db, select(Submission.id))
    total_observations = _count(db, select(Observation.id))

    pending_review_count = _count(
        db, select(ObservationModeration.id).where(ObservationModeration.status == "pending_review")
    )
    approved_count = _count(
        db, select(ObservationModeration.id).where(ObservationModeration.status == "approved")
    )
    rejected_count = _count(
        db, select(ObservationModeration.id).where(ObservationModeration.status == "rejected")
    )

    safety_critical_pending_stmt = (
        select(ObservationModeration.id)
        .join(Observation, Observation.id == ObservationModeration.observation_id)
        .join(KnowledgeTypeConfig, KnowledgeTypeConfig.id == Observation.knowledge_type_id)
        .where(
            ObservationModeration.status == "pending_review",
            KnowledgeTypeConfig.safety_critical.is_(True),
        )
    )
    safety_critical_pending_count = _count(db, safety_critical_pending_stmt)

    active_knowledge_type_count = _count(
        db, select(KnowledgeTypeConfig.id).where(KnowledgeTypeConfig.active.is_(True))
    )

    questions_generated_count = _count(
        db, select(Question.id).where(Question.status == "generated")
    )
    questions_pending_assignment_stmt = (
        select(Question.id)
        .outerjoin(QuestionAssignment, QuestionAssignment.question_id == Question.id)
        .where(Question.status == "generated", QuestionAssignment.id.is_(None))
    )
    questions_pending_assignment_count = _count(db, questions_pending_assignment_stmt)

    return AdminOverview(
        total_guides=total_guides,
        total_submissions=total_submissions,
        total_observations=total_observations,
        pending_review_count=pending_review_count,
        approved_count=approved_count,
        rejected_count=rejected_count,
        safety_critical_pending_count=safety_critical_pending_count,
        active_knowledge_type_count=active_knowledge_type_count,
        questions_generated_count=questions_generated_count,
        questions_pending_assignment_count=questions_pending_assignment_count,
    )
