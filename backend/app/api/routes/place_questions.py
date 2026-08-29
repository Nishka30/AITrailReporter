"""Popular questions (Step 18) -- the SECONDARY question source.

Kept in its own router rather than added to routes/questions.py, matching the
separation of the underlying entities: nothing here creates, ranks, assigns or
completes a knowledge-gap Question, and the existing /api/v1/questions surface
is unchanged.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.location import Location
from app.db.session import get_db
from app.schemas.place_question import (
    PlaceQuestionAnswerCreate,
    PlaceQuestionAnswerRead,
    PlaceQuestionList,
    PlaceQuestionRead,
    PlaceQuestionResearchRead,
)
from app.services import guides as guide_service
from app.services import place_question_answers as place_answer_service
from app.services import place_questions as place_question_service

router = APIRouter(tags=["place-questions"])


def _to_read(question, reward_points: int) -> PlaceQuestionRead:
    return PlaceQuestionRead(
        id=question.id,
        location_id=question.location_id,
        question_text=question.question_text,
        contribution_kind=question.contribution_kind,
        context_note=question.context_note,
        display_order=question.display_order,
        source_urls=question.source_urls,
        created_at=question.created_at,
        reward_points=reward_points,
    )


@router.get(
    "/api/v1/locations/{location_id}/popular-questions",
    response_model=PlaceQuestionList,
)
def list_location_popular_questions(
    location_id: UUID,
    db: Session = Depends(get_db),
):
    """Read-only. Never triggers a web search, so this endpoint's latency is a
    plain database read -- research is a separate, explicit action below (or
    the best-effort refresh on the guide-scoped endpoint)."""
    location = db.get(Location, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")

    questions = place_question_service.list_place_questions(db, location_id)
    research = place_question_service.get_research(db, location_id)

    return PlaceQuestionList(
        location_id=location.id,
        location_name=location.name,
        # Points resolved PER question, from its own contribution kind.
        questions=[
            _to_read(q, place_question_service.place_question_reward_points(db, q.contribution_kind))
            for q in questions
        ],
        research=(
            PlaceQuestionResearchRead.model_validate(research) if research is not None else None
        ),
    )


@router.post(
    "/api/v1/locations/{location_id}/popular-questions/research",
    response_model=PlaceQuestionList,
)
def research_location_popular_questions(
    location_id: UUID,
    force: bool = Query(
        default=False,
        description=(
            "Re-research even if the last successful run is still within the "
            "refresh window. Costs a real web search -- use deliberately."
        ),
    ),
    db: Session = Depends(get_db),
):
    """Triggers (or refreshes) web research for this place.

    Always returns 200 with the current state: 'failed' is an honest outcome
    of a successfully-handled request, not an HTTP error -- the same
    philosophy as POST .../transcribe and POST .../extract. Only a
    precondition that blocks starting an attempt at all is a 4xx/5xx.
    """
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=503,
            detail="Question research service is not configured on the server.",
        )

    try:
        place_question_service.ensure_researched(db, location_id, force=force)
    except LookupError:
        raise HTTPException(status_code=404, detail="Location not found")

    return list_location_popular_questions(location_id, db)


@router.post(
    "/api/v1/place-questions/{place_question_id}/answers",
    response_model=PlaceQuestionAnswerRead,
    status_code=201,
)
def answer_place_question(
    place_question_id: UUID,
    payload: PlaceQuestionAnswerCreate,
    response: Response,
    db: Session = Depends(get_db),
):
    """Answers a popular question. The answer becomes an ordinary Submission
    and flows through the EXISTING extraction -> observation -> moderation
    pipeline unchanged. 201 on first success, 200 on an exact idempotent
    replay -- matching create_submission/create_question/answer_question."""
    guide = guide_service.get_guide(db, payload.guide_id)
    if guide is None:
        raise HTTPException(status_code=404, detail="Guide not found")

    answered_at = payload.answered_at or datetime.now(timezone.utc)

    try:
        submission, created, points = place_answer_service.submit_place_question_answer(
            db,
            place_question_id,
            payload.guide_id,
            payload.client_answer_id,
            payload.answer_text,
            answered_at,
        )
    except place_answer_service.PlaceQuestionNotFoundError:
        raise HTTPException(status_code=404, detail="Popular question not found")
    except place_answer_service.PlaceQuestionAnswerConflictError:
        raise HTTPException(
            status_code=409,
            detail="client_answer_id was already used with different answer data",
        )

    response.status_code = 201 if created else 200
    return PlaceQuestionAnswerRead(
        place_question_id=place_question_id,
        submission_id=submission.id,
        guide_id=submission.guide_id,
        answer_text=submission.raw_text or "",
        answered_at=submission.submitted_at,
        points_awarded=points,
    )
