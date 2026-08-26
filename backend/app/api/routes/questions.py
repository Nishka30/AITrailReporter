from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas.question import QuestionCreate, QuestionRead
from app.schemas.question_answer import QuestionAnswerCreate, QuestionAnswerRead
from app.services import guides as guide_service
from app.services import knowledge_state as knowledge_state_service
from app.services import question_answers as answer_service
from app.services import questions as question_service

router = APIRouter(prefix="/api/v1/questions", tags=["questions"])


@router.post("", response_model=QuestionRead)
def create_question(payload: QuestionCreate, db: Session = Depends(get_db)):
    """Generates (or retries/replays) a question for a specific currently-
    ranked knowledge gap (Step 12) -- re-evaluates Step 10/11 fresh server-side
    rather than trusting a client-supplied gap snapshot. Always returns 200
    with the current QuestionRead -- 'processing'/'failed' are legitimate,
    honest states of a successfully-handled request, not HTTP-level errors
    (same philosophy as POST .../transcribe and POST .../extract); only a
    precondition that blocks starting an attempt at all is a 4xx/5xx. See
    services/questions.py:generate_question for the full idempotency,
    concurrency, and revalidation strategy."""
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=503, detail="Question generation service is not configured on the server."
        )

    try:
        resolved_evaluation_time = knowledge_state_service.resolve_evaluation_time(
            payload.evaluation_time
        )
    except knowledge_state_service.NaiveEvaluationTimeError:
        raise HTTPException(status_code=400, detail="evaluation_time must be timezone-aware")

    try:
        question, _outcome = question_service.generate_question(
            db,
            payload.latitude,
            payload.longitude,
            payload.knowledge_type,
            resolved_evaluation_time,
            payload.client_request_id,
        )
    except question_service.UnknownKnowledgeTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except question_service.GapNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except question_service.QuestionConflictError:
        raise HTTPException(
            status_code=409,
            detail="client_request_id was already used with a different knowledge_type/location",
        )

    return question_service.build_question_read(db, question)


@router.get("/{question_id}", response_model=QuestionRead)
def get_question(question_id: UUID, db: Session = Depends(get_db)):
    """Reads the current question state/result -- never triggers an LLM call."""
    question = question_service.get_question(db, question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    return question_service.build_question_read(db, question)


@router.post("/{question_id}/answers", response_model=QuestionRead, status_code=201)
def answer_question(
    question_id: UUID,
    payload: QuestionAnswerCreate,
    response: Response,
    db: Session = Depends(get_db),
):
    """Guide answer workflow (Step 13): persists a guide's answer to their
    currently assigned question and marks that assignment 'completed'. No LLM
    call happens here -- see services/question_answers.py for how the answer
    is made available to the EXISTING extraction pipeline instead of a second,
    parallel one. Returns the full QuestionRead (assignment + answer both
    reflect the new state) — 201 on first success, 200 on an exact idempotent
    replay, matching the create_submission/create_question convention."""
    guide = guide_service.get_guide(db, payload.guide_id)
    if guide is None:
        raise HTTPException(status_code=404, detail="Guide not found")

    resolved_answered_at = payload.answered_at or datetime.now(timezone.utc)

    try:
        _answer, created = answer_service.submit_answer(
            db,
            question_id,
            payload.guide_id,
            payload.client_answer_id,
            payload.answer_text,
            resolved_answered_at,
        )
    except answer_service.QuestionNotFoundError:
        raise HTTPException(status_code=404, detail="Question not found")
    except answer_service.NoActiveAssignmentError:
        raise HTTPException(
            status_code=400, detail="This question is not currently assigned to any guide"
        )
    except answer_service.AssignmentOwnershipError:
        raise HTTPException(
            status_code=403, detail="This question is not assigned to the given guide"
        )
    except answer_service.AssignmentCancelledError:
        raise HTTPException(status_code=400, detail="This question's assignment was cancelled")
    except answer_service.AlreadyAnsweredError:
        raise HTTPException(status_code=409, detail="This question has already been answered")
    except answer_service.AnswerConflictError:
        raise HTTPException(
            status_code=409,
            detail="client_answer_id was already used with different answer data",
        )

    response.status_code = 201 if created else 200
    question = question_service.get_question(db, question_id)
    return question_service.build_question_read(db, question)


@router.get("/{question_id}/answers/{answer_id}", response_model=QuestionAnswerRead)
def get_question_answer(question_id: UUID, answer_id: UUID, db: Session = Depends(get_db)):
    """Reads one answer directly -- e.g. to trace its submission_id for
    provenance. Most callers should just read QuestionRead.answer instead;
    this exists for the case where the answer id itself is already known."""
    answer = answer_service.get_answer(db, answer_id)
    if answer is None or answer.question_id != question_id:
        raise HTTPException(status_code=404, detail="Answer not found")
    return answer
