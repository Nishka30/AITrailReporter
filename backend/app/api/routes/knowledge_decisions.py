from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.knowledge_decision import KnowledgeDecisionResult
from app.services import knowledge_decisions as knowledge_decision_service
from app.services import knowledge_state as knowledge_state_service

router = APIRouter(prefix="/api/v1/knowledge-decisions", tags=["knowledge-decisions"])


@router.get("", response_model=KnowledgeDecisionResult)
def get_knowledge_decision(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    evaluation_time: datetime | None = Query(
        default=None,
        description="Defaults to current server time (UTC) if omitted. Must be "
        "timezone-aware if supplied.",
    ),
    db: Session = Depends(get_db),
):
    """Deterministic gap ranking + relevant-guide selection (Step 11) for one
    coordinate -- no LLM involved. Reuses Step 10's knowledge-state evaluation
    unchanged, ranks its gaps, and finds/ranks active guides whose latest
    known location is geographically relevant to each gap. `selected_guide` is
    null (never fabricated) when no relevant guide is currently available."""
    try:
        resolved_evaluation_time = knowledge_state_service.resolve_evaluation_time(evaluation_time)
    except knowledge_state_service.NaiveEvaluationTimeError:
        raise HTTPException(status_code=400, detail="evaluation_time must be timezone-aware")

    return knowledge_decision_service.evaluate_knowledge_decision(
        db, latitude, longitude, resolved_evaluation_time
    )
