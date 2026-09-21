"""Review Queue, Review Detail, and the Knowledge browser -- all built from
the SAME underlying join (Observation + its ObservationModeration +
KnowledgeTypeConfig + Submission + Guide), just filtered/scoped differently.
This join is also, deliberately, the exact shape a future public API would
reuse with `status == 'approved'` and internal-only fields dropped -- see
app/schemas/admin.py and the Phase 1 report for why no public endpoint is
built yet.

No conflict/duplicate-detection engine exists in this system (confirmed
during Phase 1 inspection) and none is invented here -- `related_observations`
in get_review_detail is a real, working "other observations of the same
knowledge type nearby" query that a human reads and judges themselves.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import Select, func, null, or_, select
from sqlalchemy.orm import Session

from app.db.geo import make_point
from app.db.models.guide import Guide
from app.db.models.knowledge_type_config import KnowledgeTypeConfig
from app.db.models.location import Location
from app.db.models.observation import Observation
from app.db.models.observation_moderation import ObservationModeration
from app.db.models.submission import Submission
from app.db.models.transcription import Transcription
from app.schemas.admin import (
    RelatedObservation,
    ReviewDetail,
    ReviewQueueItem,
    ReviewQueueResult,
    ReviewSourceSubmission,
    SiblingObservation,
)
from app.schemas.observation_moderation import ObservationModerationRead
from app.schemas.submission import SubmissionAudioRead, SubmissionPhotoRead
from app.schemas.transcription import TranscriptionRead
from app.schemas.geographic_context import NearestKnownPlace
from app.services import geographic_context as geographic_context_service
from app.services import knowledge_state as knowledge_state_service

# How recently a KnowledgeTypeConfig must have been created (Step 16, Case B:
# a dynamically-created type) to be flagged "new" for admins -- purely a
# frontend affordance, computed from the existing created_at column, no
# schema change. Arbitrary but documented, not a hidden magic number.
_NEW_KNOWLEDGE_TYPE_WINDOW = timedelta(days=14)

_SORT_COLUMNS = {
    "created_at": Observation.created_at,
    "observed_at": Observation.observed_at,
    "confidence": Observation.confidence,
}


class ReviewQueueFilters:
    def __init__(
        self,
        status: str | None = None,
        knowledge_type: str | None = None,
        safety_critical: bool | None = None,
        guide_id: UUID | None = None,
        place_id: UUID | None = None,
        source_type: str | None = None,
        q: str | None = None,
        sort: str = "created_at",
        sort_desc: bool = True,
    ):
        self.status = status
        self.knowledge_type = knowledge_type
        self.safety_critical = safety_critical
        self.guide_id = guide_id
        self.place_id = place_id
        self.source_type = source_type
        self.q = q
        self.sort = sort if sort in _SORT_COLUMNS else "created_at"
        self.sort_desc = sort_desc


def _base_query(db: Session, filters: ReviewQueueFilters) -> Select:
    stmt = (
        select(Observation, ObservationModeration, KnowledgeTypeConfig, Submission, Guide)
        .join(ObservationModeration, ObservationModeration.observation_id == Observation.id)
        .join(KnowledgeTypeConfig, KnowledgeTypeConfig.id == Observation.knowledge_type_id)
        .join(Submission, Submission.id == Observation.submission_id)
        .join(Guide, Guide.id == Observation.guide_id)
    )

    if filters.status is not None:
        stmt = stmt.where(ObservationModeration.status == filters.status)
    if filters.knowledge_type is not None:
        stmt = stmt.where(KnowledgeTypeConfig.knowledge_type == filters.knowledge_type)
    if filters.safety_critical is not None:
        stmt = stmt.where(KnowledgeTypeConfig.safety_critical == filters.safety_critical)
    if filters.guide_id is not None:
        stmt = stmt.where(Observation.guide_id == filters.guide_id)
    if filters.source_type is not None:
        stmt = stmt.where(Submission.submission_type == filters.source_type)
    if filters.q:
        pattern = f"%{filters.q}%"
        stmt = stmt.where(
            or_(Observation.evidence.ilike(pattern), Submission.raw_text.ilike(pattern))
        )
    if filters.place_id is not None:
        location = db.get(Location, filters.place_id)
        if location is not None:
            from app.core.config import settings

            stmt = stmt.where(
                Observation.geog.isnot(None),
                func.ST_DWithin(
                    Observation.geog,
                    location.geog,
                    settings.geographic_context_radius_meters,
                ),
            )
        else:
            # A place_id that doesn't resolve to a real Location should return
            # no rows, not silently ignore the filter.
            stmt = stmt.where(Observation.id.is_(None))

    return stmt


def _to_item(
    db: Session,
    observation: Observation,
    moderation: ObservationModeration,
    knowledge_type: KnowledgeTypeConfig,
    submission: Submission,
    guide: Guide,
    *,
    nearest_place: NearestKnownPlace | None = None,
) -> ReviewQueueItem:
    """Builds one ReviewQueueItem. `latitude`/`longitude` (from the
    Observation itself, copied there from its resolving Submission at
    extraction time -- see extractions.py:_resolve_observation_coordinates)
    are the observation's OWN, authoritative coordinate and are ALWAYS
    populated here at zero extra query cost -- they are already columns on
    the row this function is handed.

    `nearest_place` is real, optional PostGIS enrichment -- "is there a
    known Location nearby" -- ALREADY RESOLVED by the caller (batched for a
    whole page via geographic_context.batch_nearest_known_places, or
    single-row for a detail read via resolve_geographic_context). This
    function never queries for it itself, so it costs nothing extra to call
    per row -- that's what lets list_review_queue show every row's nearby
    place without the N+1 pattern that was deliberately removed.
    """
    is_new = (datetime.now(timezone.utc) - knowledge_type.created_at) < _NEW_KNOWLEDGE_TYPE_WINDOW
    latitude = float(observation.latitude) if observation.latitude is not None else None
    longitude = float(observation.longitude) if observation.longitude is not None else None

    nearest_known_place_name = nearest_place.name if nearest_place is not None else None
    nearest_known_place_distance_meters = (
        nearest_place.distance_meters if nearest_place is not None else None
    )

    return ReviewQueueItem(
        observation_id=observation.id,
        knowledge_type=knowledge_type.knowledge_type,
        display_name=knowledge_type.display_name,
        safety_critical=knowledge_type.safety_critical,
        value=observation.value,
        confidence=float(observation.confidence) if observation.confidence is not None else None,
        evidence=observation.evidence,
        latitude=latitude,
        longitude=longitude,
        location_label=submission.location_label,
        external_place_id=submission.external_place_id,
        observed_at=observation.observed_at,
        created_at=observation.created_at,
        submission_id=submission.id,
        submission_type=submission.submission_type,
        guide_id=guide.id,
        guide_name=guide.name,
        moderation=ObservationModerationRead.model_validate(moderation),
        nearest_known_place_name=nearest_known_place_name,
        nearest_known_place_distance_meters=nearest_known_place_distance_meters,
        knowledge_type_is_new=is_new,
    )


def list_review_queue(
    db: Session, filters: ReviewQueueFilters, page: int, page_size: int
) -> ReviewQueueResult:
    stmt = _base_query(db, filters)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    sort_column = _SORT_COLUMNS[filters.sort]
    stmt = stmt.order_by(sort_column.desc() if filters.sort_desc else sort_column.asc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    rows = db.execute(stmt).all()
    # ONE batched PostGIS query for the whole page (see
    # geographic_context.batch_nearest_known_places), not one per row --
    # this is what lets the list show a "Near <place>" caption without
    # reintroducing the N+1 pattern that was deliberately removed.
    points = {
        obs.id: (float(obs.latitude), float(obs.longitude))
        for obs, _mod, _kt, _sub, _guide in rows
        if obs.latitude is not None and obs.longitude is not None
    }
    nearest_places = geographic_context_service.batch_nearest_known_places(db, points)
    items = [
        _to_item(db, obs, mod, kt, sub, guide, nearest_place=nearest_places.get(obs.id))
        for obs, mod, kt, sub, guide in rows
    ]
    return ReviewQueueResult(items=items, total=total, page=page, page_size=page_size)


def _find_related_observations(
    db: Session, observation: Observation, knowledge_type: KnowledgeTypeConfig, limit: int = 10
) -> list[RelatedObservation]:
    """Other observations of the SAME knowledge type, ordered by recency. If
    this observation has a coordinate, scoped to that type's own configured
    geographic_relevance_radius_meters (the same radius Step 10's freshness
    evaluation uses for this type) and annotated with distance, computed in
    the SAME query (no per-row follow-up query); otherwise (no coordinate)
    falls back to recency alone, with distance left null -- never
    fabricated."""
    has_coordinate = observation.latitude is not None and observation.longitude is not None
    target = make_point(float(observation.latitude), float(observation.longitude)) if has_coordinate else None

    distance_col = func.ST_Distance(Observation.geog, target) if has_coordinate else null()

    stmt = (
        select(Observation, Guide, ObservationModeration.status, distance_col.label("distance_meters"))
        .join(Guide, Guide.id == Observation.guide_id)
        .join(ObservationModeration, ObservationModeration.observation_id == Observation.id)
        .where(
            Observation.knowledge_type_id == knowledge_type.id,
            Observation.id != observation.id,
        )
    )

    if has_coordinate:
        stmt = stmt.where(
            Observation.geog.isnot(None),
            func.ST_DWithin(
                Observation.geog, target, knowledge_type.geographic_relevance_radius_meters
            ),
        )
        stmt = stmt.order_by(distance_col)
    else:
        stmt = stmt.order_by(Observation.observed_at.desc())

    stmt = stmt.limit(limit)
    rows = db.execute(stmt).all()

    return [
        RelatedObservation(
            observation_id=obs.id,
            value=obs.value,
            confidence=float(obs.confidence) if obs.confidence is not None else None,
            evidence=obs.evidence,
            observed_at=obs.observed_at,
            guide_name=guide.name,
            distance_meters=float(distance) if distance is not None else None,
            moderation_status=moderation_status,
        )
        for obs, guide, moderation_status, distance in rows
    ]


def _find_sibling_observations(
    db: Session, observation: Observation, submission_id: UUID
) -> list[SiblingObservation]:
    stmt = (
        select(Observation, KnowledgeTypeConfig, ObservationModeration.status)
        .join(KnowledgeTypeConfig, KnowledgeTypeConfig.id == Observation.knowledge_type_id)
        .join(ObservationModeration, ObservationModeration.observation_id == Observation.id)
        .where(Observation.submission_id == submission_id, Observation.id != observation.id)
        .order_by(Observation.created_at)
    )
    rows = db.execute(stmt).all()
    return [
        SiblingObservation(
            observation_id=obs.id,
            knowledge_type=kt.knowledge_type,
            display_name=kt.display_name,
            moderation_status=status,
        )
        for obs, kt, status in rows
    ]


def get_review_detail(db: Session, observation_id: UUID) -> ReviewDetail | None:
    stmt = (
        select(Observation, ObservationModeration, KnowledgeTypeConfig, Submission, Guide)
        .join(ObservationModeration, ObservationModeration.observation_id == Observation.id)
        .join(KnowledgeTypeConfig, KnowledgeTypeConfig.id == Observation.knowledge_type_id)
        .join(Submission, Submission.id == Observation.submission_id)
        .join(Guide, Guide.id == Observation.guide_id)
        .where(Observation.id == observation_id)
    )
    row = db.execute(stmt).first()
    if row is None:
        return None
    observation, moderation, knowledge_type, submission, guide = row

    nearest_place = None
    if observation.latitude is not None and observation.longitude is not None:
        context = geographic_context_service.resolve_geographic_context(
            db, float(observation.latitude), float(observation.longitude)
        )
        nearest_place = context.nearest_known_place
    item = _to_item(
        db, observation, moderation, knowledge_type, submission, guide,
        nearest_place=nearest_place,
    )

    transcript = None
    if submission.audio is not None:
        transcription_stmt = select(Transcription).where(
            Transcription.submission_id == submission.id
        )
        transcription_row = db.execute(transcription_stmt).scalar_one_or_none()
        if transcription_row is not None:
            transcript = TranscriptionRead.model_validate(transcription_row)

    source = ReviewSourceSubmission(
        submission_id=submission.id,
        submission_type=submission.submission_type,
        raw_text=submission.raw_text,
        submitted_at=submission.submitted_at,
        audio=SubmissionAudioRead.model_validate(submission.audio) if submission.audio else None,
        photo=SubmissionPhotoRead.model_validate(submission.photo) if submission.photo else None,
        transcript=transcript,
    )

    knowledge_context = None
    if observation.latitude is not None and observation.longitude is not None:
        knowledge_context = knowledge_state_service.evaluate_knowledge_state(
            db,
            float(observation.latitude),
            float(observation.longitude),
            datetime.now(timezone.utc),
        )

    related = _find_related_observations(db, observation, knowledge_type)
    siblings = _find_sibling_observations(db, observation, submission.id)

    return ReviewDetail(
        observation=item,
        source=source,
        knowledge_context=knowledge_context,
        related_observations=related,
        sibling_observations=siblings,
    )
