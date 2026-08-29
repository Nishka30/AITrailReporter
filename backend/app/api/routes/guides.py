from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.schemas.geographic_context import GuideContext
from app.schemas.guide import GuideCreate, GuideRead, GuideUpdate
from app.schemas.guide_location import NearbyGuideResult
from app.schemas.knowledge_decision import KnowledgeDecisionResult
from app.schemas.knowledge_state import GuideKnowledgeStateResult
from app.schemas.place_question import GuidePlaceQuestions, PlaceQuestionRead
from app.schemas.question import QuestionRead
from app.schemas.reward import GuideRewardSummary
from app.services import geographic_context as geographic_context_service
from app.services import guide_locations as guide_location_service
from app.services import guides as guide_service
from app.services import knowledge_decisions as knowledge_decision_service
from app.services import knowledge_state as knowledge_state_service
from app.services import place_questions as place_question_service
from app.services import poi_discovery as poi_discovery_service
from app.services import questions as question_service
from app.services import rewards as reward_service

router = APIRouter(prefix="/api/v1/guides", tags=["guides"])


# --- background jobs -------------------------------------------------------
#
# Both web-research steps below run for MINUTES (several real web searches,
# then generation -- see place_question_research_timeout_seconds). They used to
# be awaited inline, which meant the very first guide to arrive somewhere new
# had the mobile app hang until research finished or timed out. Since both are
# cached for weeks afterwards, that cost fell entirely on one unlucky request
# for a benefit every LATER request collects.
#
# So they are scheduled instead: the endpoint answers immediately with whatever
# is known right now, and the work lands before the next refresh. That makes
# "nothing here yet" a normal, momentary state rather than a stall, which is
# also how the app already renders it.
#
# Each job opens its OWN session: the request's session is closed by the
# get_db dependency as soon as the response is sent, so reusing it here would
# operate on a dead connection.


def _discover_places_job(latitude: float, longitude: float) -> None:
    db = SessionLocal()
    try:
        poi_discovery_service.maybe_ensure_discovered(db, latitude, longitude)
    finally:
        db.close()


def _research_place_questions_job(location_id: UUID) -> None:
    db = SessionLocal()
    try:
        place_question_service.maybe_ensure_researched(db, location_id)
    finally:
        db.close()


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


@router.get("/{guide_id}/popular-questions", response_model=GuidePlaceQuestions)
def get_guide_popular_questions(
    guide_id: UUID,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Popular questions about the place the guide is currently at (Step 18).

    This is the SECONDARY question source and is deliberately separate from
    `/questions` above -- it does not touch gap ranking, and an empty result
    here never affects the priority queue.

    Resolves the guide's place with the EXISTING geographic-context rule
    (nearest known Location within `geographic_context_radius_meters`,
    unchanged), then best-effort refreshes research if it is stale. Never
    404s on a missing location or an out-of-range position: those are ordinary
    situations for a guide in the field, reported as an empty list with null
    location fields so the app can say "we don't know where you are" rather
    than showing questions about somewhere they aren't.
    """
    guide = guide_service.get_guide(db, guide_id)
    if guide is None:
        raise HTTPException(status_code=404, detail="Guide not found")

    empty = GuidePlaceQuestions(
        location_id=None, location_name=None, distance_meters=None, questions=[]
    )

    location = guide_location_service.get_latest_location(db, guide_id)
    if location is None:
        return empty

    latitude, longitude = float(location.latitude), float(location.longitude)
    context = geographic_context_service.resolve_geographic_context(db, latitude, longitude)
    place = context.nearest_known_place
    if place is None:
        # No known place within range. Historically this was simply the end of
        # the road -- and with an empty `locations` table it was the end of the
        # road EVERYWHERE, which is why production served nothing but generic
        # prompts however good the research prompts were.
        #
        # Now it schedules discovery for this part of the map instead. This
        # request still returns empty (honestly -- we genuinely don't know where
        # they are yet), but the next one has real places to work with. Cached
        # per grid cell, so a whole neighbourhood costs one run, not one per
        # guide and not one per GPS reading.
        background.add_task(_discover_places_job, latitude, longitude)
        return empty

    # Scheduled rather than awaited: research takes minutes and is cached for
    # 30 days afterwards, so blocking this request would stall the app for one
    # guide to benefit all the later ones. is_research_stale is re-checked
    # inside the job, so scheduling on every request costs nothing once fresh.
    if place_question_service.is_research_stale(
        place_question_service.get_research(db, place.id)
    ):
        background.add_task(_research_place_questions_job, place.id)

    questions = place_question_service.list_place_questions(db, place.id)

    return GuidePlaceQuestions(
        location_id=place.id,
        location_name=place.name,
        distance_meters=place.distance_meters,
        questions=[
            PlaceQuestionRead(
                id=q.id,
                location_id=q.location_id,
                question_text=q.question_text,
                contribution_kind=q.contribution_kind,
                context_note=q.context_note,
                display_order=q.display_order,
                source_urls=q.source_urls,
                created_at=q.created_at,
                # Resolved PER question from its own contribution kind, so a
                # photo request and a status check are not paid the same.
                reward_points=place_question_service.place_question_reward_points(
                    db, q.contribution_kind
                ),
            )
            for q in questions
        ],
    )


@router.get("/{guide_id}/rewards", response_model=GuideRewardSummary)
def get_guide_rewards(guide_id: UUID, db: Session = Depends(get_db)):
    """This guide's authoritative reward state (Step 18). Every figure is
    computed from the append-only ledger at request time -- the backend is the
    source of truth, and the app's offline provisional total is superseded by
    whatever this returns."""
    guide = guide_service.get_guide(db, guide_id)
    if guide is None:
        raise HTTPException(status_code=404, detail="Guide not found")
    return reward_service.get_guide_rewards(db, guide_id)
