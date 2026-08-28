"""Read-only admin visibility into the EXISTING Question/QuestionAssignment
lifecycle (Step 12/13) -- does not touch or redesign that workflow, per the
admin dashboard spec's explicit instruction. Only ever reads; question
generation and assignment logic stays entirely in app/services/questions.py.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.guide import Guide
from app.db.models.knowledge_type_config import KnowledgeTypeConfig
from app.db.models.question import Question
from app.db.models.question_assignment import QuestionAssignment
from app.schemas.admin import AdminQuestionSummary


def list_admin_questions(
    db: Session,
    status: str | None = None,
    assignment_status: str | None = None,
    safety_critical: bool | None = None,
    limit: int = 100,
) -> list[AdminQuestionSummary]:
    # Latest assignment per question -- same DISTINCT ON pattern as
    # app/services/guide_locations.py::find_nearby_guides, since a question
    # could in principle have more than one assignment row over time
    # (reassignment; current code only ever creates one, but this listing
    # doesn't assume that).
    latest_assignment = (
        select(
            QuestionAssignment.question_id,
            QuestionAssignment.status.label("assignment_status"),
            QuestionAssignment.guide_id,
        )
        .distinct(QuestionAssignment.question_id)
        .order_by(QuestionAssignment.question_id, QuestionAssignment.assigned_at.desc())
        .subquery()
    )

    stmt = (
        select(Question, KnowledgeTypeConfig, latest_assignment.c.assignment_status, Guide.name)
        .join(KnowledgeTypeConfig, KnowledgeTypeConfig.id == Question.knowledge_type_id)
        .outerjoin(latest_assignment, latest_assignment.c.question_id == Question.id)
        .outerjoin(Guide, Guide.id == latest_assignment.c.guide_id)
    )

    if status is not None:
        stmt = stmt.where(Question.status == status)
    if assignment_status is not None:
        stmt = stmt.where(latest_assignment.c.assignment_status == assignment_status)
    if safety_critical is not None:
        stmt = stmt.where(Question.safety_critical == safety_critical)

    stmt = stmt.order_by(Question.created_at.desc()).limit(limit)

    rows = db.execute(stmt).all()
    return [
        AdminQuestionSummary(
            question_id=question.id,
            knowledge_type=knowledge_type.knowledge_type,
            display_name=knowledge_type.display_name,
            gap_state=question.gap_state,
            status=question.status,
            safety_critical=question.safety_critical,
            target_latitude=float(question.target_latitude),
            target_longitude=float(question.target_longitude),
            nearest_known_place_name=question.nearest_known_place_name,
            question_text=question.question_text,
            assignment_status=assignment_status,
            assigned_guide_name=guide_name,
            created_at=question.created_at,
        )
        for question, knowledge_type, assignment_status, guide_name in rows
    ]
