from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.geographic_context import GuideContext
from app.schemas.guide import GuideCreate, GuideRead, GuideUpdate
from app.schemas.guide_location import NearbyGuideResult
from app.schemas.knowledge_decision import KnowledgeDecisionResult
from app.schemas.knowledge_state import GuideKnowledgeStateResult
from app.schemas.question import QuestionRead
from app.services import geographic_context as geographic_context_service
from app.services import guide_locations as guide_location_service
from app.services import guides as guide_service
from app.services import knowledge_decisions as knowledge_decision_service
from app.services import knowledge_state as knowledge_state_service
from app.services import questions as question_service

router = APIRouter(prefix="/api/v1/guides", tags=["guides"])


@router.post("", response_model=GuideRead, status_code=201)
def create_guide(payload: GuideCreate, response: Response, db: Session = Depends(get_db)):
    """Creates a guide. If payload.client_guide_id was already used, this is
    idempotent: the existing guide is returned with 200 instead of creating a
    duplicate (which would otherwise return 201)."""
    guide, created = guide_service.create_or_get_guide(db, payload)
    response.status_code = 201 if created else 200
    return guide


# Registered before "/{guide_id}" so the literal path "nearby" is matched first —
# otherwise it would be swallowed by the {guide_id} route and fail UUID parsing.
@router.get("/nearby", response_model=list[NearbyGuideResult])
def get_nearby_guides(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    radius_meters: float = Query(gt=0),
    db: Session = Depends(get_db),
):
    return guide_location_service.find_nearby_guides(db, latitude, longitude, radius_meters)


@router.get("/{guide_id}", response_model=GuideRead)
def get_guide(guide_id: UUID, db: Session = Depends(get_db)):
    guide = guide_service.get_guide(db, guide_id)
    if guide is None:
        raise HTTPException(status_code=404, detail="Guide not found")
    return guide


@router.patch("/{guide_id}", response_model=GuideRead)
def update_guide(guide_id: UUID, payload: GuideUpdate, db: Session = Depends(get_db)):
    """Updates a guide's editable identity fields (Step 17: the mobile Profile
    screen). Partial — only the fields present in the request body are written.

    Accepts ONLY name and phone_number. The Profile screen's "About you" text
    and profile photo are never sent here and have no server representation at
    all; see GuideUpdate for the privacy reasoning.

    Naturally idempotent: applying the same body twice leaves the same state, so
    unlike the creation endpoints this needs no client-generated id. The mobile
    app retries it from its normal offline outbox on failure (see
    mobile/src/sync/syncService.ts)."""
    guide = guide_service.update_guide(db, guide_id, payload)
    if guide is None:
        raise HTTPException(status_code=404, detail="Guide not found")
    return guide


@router.get("/{guide_id}/context", response_model=GuideContext)
def get_guide_context(guide_id: UUID, db: Session = Depends(get_db)):
    guide = guide_service.get_guide(db, guide_id)
    if guide is None:
        raise HTTPException(status_code=404, detail="Guide not found")

    location = guide_location_service.get_latest_location(db, guide_id)
    if location is None:
        raise HTTPException(status_code=404, detail="No location recorded for this guide")

    latitude = float(location.latitude)
    longitude = float(location.longitude)
    context = geographic_context_service.resolve_geographic_context(db, latitude, longitude)

    return GuideContext(
        guide_id=guide.id,
        guide_name=guide.name,
        latitude=latitude,
        longitude=longitude,
        recorded_at=location.recorded_at,
        accuracy_meters=location.accuracy_meters,
        nearest_known_place=context.nearest_known_place,
    )


@router.get("/{guide_id}/knowledge-state", response_model=GuideKnowledgeStateResult)
def get_guide_knowledge_state(
    guide_id: UUID,
    evaluation_time: datetime | None = Query(
        default=None,
        description="Defaults to current server time (UTC) if omitted. Must be "
        "timezone-aware if supplied.",
    ),
    db: Session = Depends(get_db),
):
    """Deterministic knowledge freshness/staleness/gap evaluation (Step 10) at
    the guide's OWN latest GPS location -- resolved the identical way
    `/context` above resolves it: latest GuideLocation by recorded_at (never
    insertion order). 404 if the guide doesn't exist, or exists but has no
    recorded location yet (same error text as `/context` and
    `/locations/latest`, for consistency)."""
    guide = guide_service.get_guide(db, guide_id)
    if guide is None:
        raise HTTPException(status_code=404, detail="Guide not found")

    location = guide_location_service.get_latest_location(db, guide_id)
    if location is None:
        raise HTTPException(status_code=404, detail="No location recorded for this guide")

    try:
        resolved_evaluation_time = knowledge_state_service.resolve_evaluation_time(evaluation_time)
    except knowledge_state_service.NaiveEvaluationTimeError:
        raise HTTPException(status_code=400, detail="evaluation_time must be timezone-aware")

    latitude = float(location.latitude)
    longitude = float(location.longitude)
    knowledge_state = knowledge_state_service.evaluate_knowledge_state(
        db, latitude, longitude, resolved_evaluation_time
    )
    context = geographic_context_service.resolve_geographic_context(db, latitude, longitude)

    return GuideKnowledgeStateResult(
        guide_id=guide.id,
        location_recorded_at=location.recorded_at,
        nearest_known_place=context.nearest_known_place,
        knowledge_state=knowledge_state,
    )


@router.get("/{guide_id}/knowledge-decisions", response_model=KnowledgeDecisionResult)
def get_guide_knowledge_decision(
    guide_id: UUID,
    evaluation_time: datetime | None = Query(
        default=None,
        description="Defaults to current server time (UTC) if omitted. Must be "
        "timezone-aware if supplied.",
    ),
    db: Session = Depends(get_db),
):
    """Deterministic gap ranking + relevant-guide selection (Step 11) at the
    guide's OWN latest GPS location -- resolved identically to `/context` and
    `/knowledge-state` above (latest GuideLocation by recorded_at, never
    insertion order). Same 404s as `/knowledge-state`. Note the requesting
    guide can itself appear as a candidate guide for a gap near their own
    location -- this endpoint answers "what's the current decision state
    around me," not "what should I be asked," so that isn't filtered out."""
    guide = guide_service.get_guide(db, guide_id)
    if guide is None:
        raise HTTPException(status_code=404, detail="Guide not found")

    location = guide_location_service.get_latest_location(db, guide_id)
    if location is None:
        raise HTTPException(status_code=404, detail="No location recorded for this guide")

    try:
        resolved_evaluation_time = knowledge_state_service.resolve_evaluation_time(evaluation_time)
    except knowledge_state_service.NaiveEvaluationTimeError:
        raise HTTPException(status_code=400, detail="evaluation_time must be timezone-aware")

    return knowledge_decision_service.evaluate_knowledge_decision(
        db, float(location.latitude), float(location.longitude), resolved_evaluation_time
    )


@router.get("/{guide_id}/questions", response_model=list[QuestionRead])
def get_guide_questions(
    guide_id: UUID,
    status: Literal["assigned", "active", "completed", "cancelled"] | None = Query(
        default=None, description="Filter by ASSIGNMENT status (not question generation status)."
    ),
    db: Session = Depends(get_db),
):
    """Questions currently assigned to this guide (Step 12), most recently
    assigned first. Read-only -- never triggers generation. 404 only if the
    guide itself doesn't exist; an existing guide with no assignments simply
    returns an empty list (not an error -- no location is required either,
    unlike /context and /knowledge-state, since this doesn't evaluate
    anything)."""
    guide = guide_service.get_guide(db, guide_id)
    if guide is None:
        raise HTTPException(status_code=404, detail="Guide not found")

    questions = question_service.list_questions_for_guide(db, guide_id, status)
    return [question_service.build_question_read(db, q) for q in questions]
