"""Public traveller website content layer (read-only, unauthenticated).

Every query in this module is hard-filtered to
ObservationModeration.status == 'approved' -- there is no code path here
that can return a pending/rejected Observation, or a Guide's phone number,
or a raw storage key. This mirrors the join pattern in
app/services/admin_review.py (that module's docstring explicitly names this
as the intended future reuse) and app/services/admin_places.py, just scoped
down to what's safe for an anonymous public audience.

Freshness/staleness math is NOT reimplemented here. evaluate_public_knowledge_state
reuses knowledge_state.py's own `_evaluate_one_type` boundary logic unchanged,
swapping in an approved-only "latest relevant observation" lookup so a
pending or rejected report can never influence what a traveller is told is
true right now -- see that function's docstring for why a separate lookup
(rather than reusing evaluate_knowledge_state directly) is necessary.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.geo import make_point
from app.db.models.guide import Guide
from app.db.models.knowledge_type_config import KnowledgeTypeConfig
from app.db.models.location import Location
from app.db.models.observation import Observation
from app.db.models.observation_moderation import ObservationModeration
from app.db.models.submission import Submission
from app.db.models.transcription import Transcription
from app.schemas.public import (
    PublicConditionState,
    PublicKnowledgeType,
    PublicLocationDetail,
    PublicLocationSummary,
    PublicObservation,
    PublicObservationList,
    PublicSearchResult,
)
from app.services import geographic_context as geographic_context_service
from app.services import knowledge_state as knowledge_state_service
from app.services import knowledge_types as knowledge_type_service

_SEARCH_LIMIT = 20


def _find_latest_approved_relevant_observation(
    db: Session, knowledge_type_id, target_point, radius_meters: float
) -> tuple[Observation | None, float | None]:
    """Same access pattern as knowledge_state.py's private
    _find_latest_relevant_observation (latest, within this type's own
    radius, via PostGIS ST_DWithin), with one addition: joined to
    ObservationModeration and filtered to status == 'approved'. This is the
    ONLY difference from the internal engine -- the guide/admin-facing
    knowledge state deliberately considers every observation regardless of
    moderation (a guide shouldn't have to wait for admin approval to see
    that a gap was just filled); the public site must never let an
    unapproved report's timing leak into what it displays as true."""
    distance = func.ST_Distance(Observation.geog, target_point).label("distance_meters")
    stmt = (
        select(Observation, distance)
        .join(ObservationModeration, ObservationModeration.observation_id == Observation.id)
        .where(
            Observation.knowledge_type_id == knowledge_type_id,
            ObservationModeration.status == "approved",
            func.ST_DWithin(Observation.geog, target_point, radius_meters),
        )
        .order_by(Observation.observed_at.desc())
        .limit(1)
    )
    row = db.execute(stmt).first()
    if row is None:
        return None, None
    observation, distance_meters = row
    return observation, float(distance_meters)


def evaluate_public_knowledge_state(
    db: Session, latitude: float, longitude: float, evaluation_time: datetime
) -> list[PublicConditionState]:
    target_point = make_point(latitude, longitude)
    active_types = knowledge_type_service.get_active_knowledge_types(db)

    states: list[PublicConditionState] = []
    for kt in active_types:
        observation, _distance = _find_latest_approved_relevant_observation(
            db, kt.id, target_point, kt.geographic_relevance_radius_meters
        )
        internal = knowledge_state_service._evaluate_one_type(  # noqa: SLF001 -- deliberate reuse, see module docstring
            kt, observation, _distance, evaluation_time
        )
        states.append(
            PublicConditionState(
                knowledge_type=internal.knowledge_type,
                display_name=internal.display_name,
                safety_critical=internal.safety_critical,
                state=internal.state,
                observed_at=internal.observed_at,
                age_hours=internal.age_hours,
                severity_hours=internal.severity_hours,
                latest_observation_id=internal.latest_observation_id,
            )
        )
    return states


def _approved_observation_query() -> Select:
    return (
        select(Observation, KnowledgeTypeConfig, Submission, Guide, Transcription)
        .join(ObservationModeration, ObservationModeration.observation_id == Observation.id)
        .join(KnowledgeTypeConfig, KnowledgeTypeConfig.id == Observation.knowledge_type_id)
        .join(Submission, Submission.id == Observation.submission_id)
        .join(Guide, Guide.id == Observation.guide_id)
        .outerjoin(Transcription, Transcription.submission_id == Submission.id)
        .where(ObservationModeration.status == "approved")
    )


def _to_public_observation(
    db: Session,
    observation: Observation,
    knowledge_type: KnowledgeTypeConfig,
    submission: Submission,
    guide: Guide,
    transcription: Transcription | None,
) -> PublicObservation:
    transcript = (
        transcription.transcript
        if transcription is not None and transcription.status == "completed"
        else None
    )
    nearest_place_id = None
    nearest_place_name = None
    if observation.latitude is not None and observation.longitude is not None:
        context = geographic_context_service.resolve_geographic_context(
            db, float(observation.latitude), float(observation.longitude)
        )
        if context.nearest_known_place is not None:
            nearest_place_id = context.nearest_known_place.id
            nearest_place_name = context.nearest_known_place.name
    return PublicObservation(
        observation_id=observation.id,
        knowledge_type=knowledge_type.knowledge_type,
        display_name=knowledge_type.display_name,
        safety_critical=knowledge_type.safety_critical,
        value=observation.value,
        evidence=observation.evidence,
        observed_at=observation.observed_at,
        submission_type=submission.submission_type,
        guide_name=guide.name,
        has_photo=submission.photo is not None,
        has_audio=submission.audio is not None,
        photo_url=f"/api/v1/public/media/{submission.id}/photo" if submission.photo is not None else None,
        audio_url=f"/api/v1/public/media/{submission.id}/audio" if submission.audio is not None else None,
        transcript=transcript,
        nearest_place_id=nearest_place_id,
        nearest_place_name=nearest_place_name,
    )


def list_public_observations(
    db: Session,
    location_id: UUID | None = None,
    knowledge_type: str | None = None,
    has_photo: bool | None = None,
    has_audio: bool | None = None,
    limit: int = 25,
    offset: int = 0,
) -> PublicObservationList:
    stmt = _approved_observation_query()

    if location_id is not None:
        location = db.get(Location, location_id)
        if location is None:
            return PublicObservationList(items=[], total=0)
        stmt = stmt.where(
            Observation.geog.isnot(None),
            func.ST_DWithin(
                Observation.geog, location.geog, settings.geographic_context_radius_meters
            ),
        )
    if knowledge_type is not None:
        stmt = stmt.where(KnowledgeTypeConfig.knowledge_type == knowledge_type)
    if has_photo:
        stmt = stmt.where(Submission.photo_storage_key.isnot(None))
    if has_audio:
        stmt = stmt.where(Submission.audio_storage_key.isnot(None))

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    stmt = stmt.order_by(Observation.observed_at.desc()).offset(offset).limit(limit)
    rows = db.execute(stmt).all()
    items = [_to_public_observation(db, obs, kt, sub, guide, tr) for obs, kt, sub, guide, tr in rows]
    return PublicObservationList(items=items, total=total)


def get_public_observation(db: Session, observation_id: UUID) -> PublicObservation | None:
    stmt = _approved_observation_query().where(Observation.id == observation_id)
    row = db.execute(stmt).first()
    if row is None:
        return None
    obs, kt, sub, guide, tr = row
    return _to_public_observation(db, obs, kt, sub, guide, tr)


def list_public_locations(db: Session, limit: int = 50) -> list[PublicLocationSummary]:
    """One row per Location with its nearby APPROVED observation count and
    last activity time, computed in a single grouped query (same technique
    as admin_places.list_places) so 'recently updated' discovery sorting
    never requires an evaluate_public_knowledge_state() call per row."""
    radius = settings.geographic_context_radius_meters
    # Two outer joins so a Location with zero (or zero APPROVED) nearby
    # observations still appears with a count of 0, never dropped. The
    # second join's ON clause folds the approval filter directly into the
    # join condition (rather than a WHERE, which would turn the outer join
    # into an inner one) -- a non-approved or non-existent nearby observation
    # simply leaves ObservationModeration.observation_id NULL for that row,
    # which COUNT()/MAX(CASE...) below then correctly ignore.
    approved_activity = case(
        (ObservationModeration.observation_id.isnot(None), Observation.observed_at),
        else_=None,
    )
    stmt = (
        select(
            Location.id,
            Location.name,
            Location.description,
            Location.latitude,
            Location.longitude,
            func.count(ObservationModeration.observation_id).label("approved_count"),
            func.max(approved_activity).label("last_activity_at"),
        )
        .outerjoin(
            Observation,
            (Observation.geog.isnot(None)) & (func.ST_DWithin(Observation.geog, Location.geog, radius)),
        )
        .outerjoin(
            ObservationModeration,
            (ObservationModeration.observation_id == Observation.id)
            & (ObservationModeration.status == "approved"),
        )
        .group_by(Location.id, Location.name, Location.description, Location.latitude, Location.longitude)
        .order_by(func.max(approved_activity).desc().nulls_last(), Location.name)
        .limit(limit)
    )
    rows = db.execute(stmt).all()
    return [
        PublicLocationSummary(
            location_id=row.id,
            name=row.name,
            description=row.description,
            latitude=float(row.latitude),
            longitude=float(row.longitude),
            approved_observation_count=row.approved_count,
            last_activity_at=row.last_activity_at,
        )
        for row in rows
    ]


def get_public_location_detail(
    db: Session, location_id: UUID, evaluation_time: datetime, observation_limit: int = 30
) -> PublicLocationDetail | None:
    location = db.get(Location, location_id)
    if location is None:
        return None

    conditions = evaluate_public_knowledge_state(
        db, float(location.latitude), float(location.longitude), evaluation_time
    )
    observations = list_public_observations(
        db, location_id=location_id, limit=observation_limit
    )
    photo_count = sum(1 for o in observations.items if o.has_photo)
    voice_story_count = sum(1 for o in observations.items if o.has_audio)

    return PublicLocationDetail(
        location_id=location.id,
        name=location.name,
        description=location.description,
        latitude=float(location.latitude),
        longitude=float(location.longitude),
        approved_observation_count=observations.total,
        last_activity_at=observations.items[0].observed_at if observations.items else None,
        conditions=conditions,
        recent_observations=observations.items,
        photo_count=photo_count,
        voice_story_count=voice_story_count,
    )


def list_public_knowledge_types(db: Session) -> list[PublicKnowledgeType]:
    return [
        PublicKnowledgeType(
            knowledge_type=kt.knowledge_type,
            display_name=kt.display_name,
            safety_critical=kt.safety_critical,
        )
        for kt in knowledge_type_service.get_active_knowledge_types(db)
    ]


def search_public(db: Session, q: str, limit: int = _SEARCH_LIMIT) -> PublicSearchResult:
    pattern = f"%{q}%"

    location_stmt = (
        select(Location)
        .where(or_(Location.name.ilike(pattern), Location.description.ilike(pattern)))
        .order_by(Location.name)
        .limit(limit)
    )
    locations = db.execute(location_stmt).scalars().all()
    location_summaries = list_public_locations(db, limit=200)
    location_summary_by_id = {ls.location_id: ls for ls in location_summaries}
    matched_locations = [
        location_summary_by_id.get(loc.id)
        or PublicLocationSummary(
            location_id=loc.id,
            name=loc.name,
            description=loc.description,
            latitude=float(loc.latitude),
            longitude=float(loc.longitude),
            approved_observation_count=0,
            last_activity_at=None,
        )
        for loc in locations
    ]

    obs_stmt = (
        _approved_observation_query()
        .where(or_(Observation.evidence.ilike(pattern), Submission.raw_text.ilike(pattern)))
        .order_by(Observation.observed_at.desc())
        .limit(limit)
    )
    obs_rows = db.execute(obs_stmt).all()
    matched_observations = [
        _to_public_observation(db, obs, kt, sub, guide, tr) for obs, kt, sub, guide, tr in obs_rows
    ]

    return PublicSearchResult(
        query=q, locations=matched_locations, observations=matched_observations
    )
