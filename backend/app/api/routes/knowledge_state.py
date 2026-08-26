from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.knowledge_state import KnowledgeStateResult
from app.services import knowledge_state as knowledge_state_service

router = APIRouter(prefix="/api/v1/knowledge-state", tags=["knowledge-state"])


@router.get("", response_model=KnowledgeStateResult)
def get_knowledge_state(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    evaluation_time: datetime | None = Query(
        default=None,
        description="Defaults to current server time (UTC) if omitted. Must be "
        "timezone-aware if supplied.",
    ),
    db: Session = Depends(get_db),
):
    """Deterministic knowledge freshness/staleness/gap evaluation for one
    coordinate (Step 10) -- no LLM involved. For every active knowledge type:
    missing (no geographically-relevant observation), fresh, or stale, each
    judged against THAT type's own configured freshness window and geographic
    relevance radius (never one global threshold)."""
    try:
        resolved_evaluation_time = knowledge_state_service.resolve_evaluation_time(evaluation_time)
    except knowledge_state_service.NaiveEvaluationTimeError:
        raise HTTPException(status_code=400, detail="evaluation_time must be timezone-aware")

    return knowledge_state_service.evaluate_knowledge_state(
        db, latitude, longitude, resolved_evaluation_time
    )
