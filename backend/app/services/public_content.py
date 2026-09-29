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

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.geo import make_point
from app.db.models.category_knowledge import CategoryKnowledge
from app.db.models.guide import Guide
from app.db.models.knowledge_type_config import KnowledgeTypeConfig
from app.db.models.location import Location
from app.db.models.location_category import LocationCategory, LocationCategoryAssignment
from app.db.models.observation import Observation
from app.db.models.observation_moderation import ObservationModeration
from app.db.models.place_question import PlaceQuestion
from app.db.models.route import Route, RouteStop
from app.db.models.submission import Submission
from app.db.models.submission_photo import SubmissionPhoto
from app.db.models.submission_review import SubmissionReview
from app.db.models.transcription import Transcription
from app.schemas.knowledge_state import KnowledgeState
from app.schemas.public import (
    PublicCategoryLabel,
    PublicConditionState,
    PublicKnowledgeType,
    PublicLocationCategory,
    PublicLocationDetail,
    PublicLocationSummary,
    PublicObservation,
    PublicObservationList,
    PublicPlaceQuestion,
    PublicPlaceQuestionAnswer,
    PublicRoute,
    PublicRouteStop,
    PublicSearchResult,
    PublicVerifiedKnowledge,
)
from app.services import category_knowledge as category_knowledge_service
from app.services import geographic_context as geographic_context_service
from app.services import knowledge_state as knowledge_state_service
from app.services import knowledge_types as knowledge_type_service
from app.services import place_questions as place_questions_service
from app.services import place_summary_service
from app.services import submissions as submission_service

_SEARCH_LIMIT = 20

# How many of a PlaceQuestion's most-recent approved answers to surface --
# a public reader wants a representative sample, not every answer ever given.
_ANSWERS_PER_QUESTION_LIMIT = 3

# Catalog catch-all slugs that describe nothing a traveller could act on --
# omitted from a public Location's categories (see
# list_public_location_categories). A sentinel, not a curated list of "good"
# categories: every real category still comes straight from the database.
_NON_DESCRIPTIVE_CATEGORY_SLUGS = frozenset({"other"})


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
    """Rows of (Observation, KnowledgeTypeConfig | None, Submission, Guide,
    Transcription | None, LocationCategory | None).

    BOTH knowledge systems' observations are included: every Observation has
    exactly one of knowledge_type_id / category_knowledge_id (the
    ck_observations_exactly_one_knowledge_target CHECK), so the knowledge-
    type side and the category side are OUTER joins -- an inner join on
    KnowledgeTypeConfig (as this query originally had) silently dropped every
    category-knowledge observation from the public site."""
    return (
        select(Observation, KnowledgeTypeConfig, Submission, Guide, Transcription, LocationCategory)
        .join(ObservationModeration, ObservationModeration.observation_id == Observation.id)
        .outerjoin(KnowledgeTypeConfig, KnowledgeTypeConfig.id == Observation.knowledge_type_id)
        .outerjoin(CategoryKnowledge, CategoryKnowledge.id == Observation.category_knowledge_id)
        .outerjoin(
            LocationCategoryAssignment,
            LocationCategoryAssignment.id == CategoryKnowledge.category_assignment_id,
        )
        .outerjoin(LocationCategory, LocationCategory.id == LocationCategoryAssignment.category_id)
        .join(Submission, Submission.id == Observation.submission_id)
        .join(Guide, Guide.id == Observation.guide_id)
        .outerjoin(Transcription, Transcription.submission_id == Submission.id)
        .where(ObservationModeration.status == "approved")
    )


def _to_public_observation(
    db: Session,
    observation: Observation,
    knowledge_type: KnowledgeTypeConfig | None,
    submission: Submission,
    guide: Guide,
    transcription: Transcription | None,
    category: LocationCategory | None = None,
    *,
    include_nearest_place: bool = False,
) -> PublicObservation:
    """latitude/longitude/location_label/external_place_id are the
    observation's OWN authoritative location -- always populated here at
    zero extra query cost, straight off columns already present on the rows
    this function is handed. This is the field the future Travelers website
    (and this backend's own callers) should plot on a map; it is NEVER
    replaced or hidden by nearest_place_id/_name below.

    nearest_place_id/_name are OPTIONAL PostGIS enrichment -- "is there a
    known Location nearby" -- and are only resolved when
    include_nearest_place=True. Defaults to False so a paginated/bounded list
    (list_public_observations, search_public) never pays for a PostGIS query
    per row per page load; only get_public_observation (exactly one row)
    opts in.
    """
    transcript = (
        transcription.transcript
        if transcription is not None and transcription.status == "completed"
        else None
    )
    latitude = float(observation.latitude) if observation.latitude is not None else None
    longitude = float(observation.longitude) if observation.longitude is not None else None
    nearest_place_id = None
    nearest_place_name = None
    if include_nearest_place and latitude is not None and longitude is not None:
        context = geographic_context_service.resolve_geographic_context(db, latitude, longitude)
        if context.nearest_known_place is not None:
            nearest_place_id = context.nearest_known_place.id
            nearest_place_name = context.nearest_known_place.name
    photos = submission_service.list_submission_photos(db, submission.id)
    if knowledge_type is not None:
        type_key, type_label, safety_critical = (
            knowledge_type.knowledge_type,
            knowledge_type.display_name,
            knowledge_type.safety_critical,
        )
    elif category is not None:
        type_key, type_label, safety_critical = category.slug, category.display_name, False
    else:
        # Unreachable under the CHECK constraint (a category observation
        # always resolves to its category via FK chain); kept honest rather
        # than raising mid-page.
        type_key, type_label, safety_critical = "other", "Report", False
    return PublicObservation(
        observation_id=observation.id,
        knowledge_type=type_key,
        display_name=type_label,
        safety_critical=safety_critical,
        category_slug=category.slug if knowledge_type is None and category is not None else None,
        category_display_name=(
            category.display_name if knowledge_type is None and category is not None else None
        ),
        value=observation.value,
        evidence=observation.evidence,
        observed_at=observation.observed_at,
        submission_type=submission.submission_type,
        guide_name=guide.name,
        latitude=latitude,
        longitude=longitude,
        location_label=submission.location_label,
        external_place_id=submission.external_place_id,
        has_photo=bool(photos),
        has_audio=submission.audio is not None,
        photo_urls=[f"/api/v1/public/media/{submission.id}/photos/{photo.id}" for photo in photos],
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
        stmt = stmt.where(
            Submission.id.in_(select(SubmissionPhoto.submission_id))
        )
    if has_audio:
        stmt = stmt.where(Submission.audio_storage_key.isnot(None))

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    stmt = stmt.order_by(Observation.observed_at.desc()).offset(offset).limit(limit)
    rows = db.execute(stmt).all()
    items = [
        _to_public_observation(db, obs, kt, sub, guide, tr, cat) for obs, kt, sub, guide, tr, cat in rows
    ]
    return PublicObservationList(items=items, total=total)


def get_public_observation(db: Session, observation_id: UUID) -> PublicObservation | None:
    stmt = _approved_observation_query().where(Observation.id == observation_id)
    row = db.execute(stmt).first()
    if row is None:
        return None
    obs, kt, sub, guide, tr, cat = row
    return _to_public_observation(db, obs, kt, sub, guide, tr, cat, include_nearest_place=True)


def list_public_locations(
    db: Session,
    limit: int = 50,
    *,
    near: Location | None = None,
    near_radius_meters: float | None = None,
) -> list[PublicLocationSummary]:
    """One row per Location with its nearby APPROVED observation count and
    last activity time, computed in a single grouped query (same technique
    as admin_places.list_places) so 'recently updated' discovery sorting
    never requires an evaluate_public_knowledge_state() call per row.

    With `near`, the same rows restricted to OTHER Locations within
    near_radius_meters of that Location, ordered nearest first, each carrying
    distance_meters -- a Location page's "Nearby places"."""
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
        .limit(limit)
    )
    if near is None:
        stmt = stmt.order_by(func.max(approved_activity).desc().nulls_last(), Location.name)
    else:
        # Location.geog is functionally dependent on the grouped primary key,
        # so it's usable in the select list/ORDER BY without joining the group.
        anchor = make_point(float(near.latitude), float(near.longitude))
        distance = func.ST_Distance(Location.geog, anchor)
        stmt = (
            stmt.add_columns(distance.label("distance_meters"))
            .where(
                Location.id != near.id,
                func.ST_DWithin(
                    Location.geog, anchor, near_radius_meters or settings.public_nearby_radius_meters
                ),
            )
            .order_by(distance, Location.name)
        )
    rows = db.execute(stmt).all()
    labels_by_location = _category_labels_by_location(db, [row.id for row in rows])
    return [
        PublicLocationSummary(
            location_id=row.id,
            name=row.name,
            description=row.description,
            latitude=float(row.latitude),
            longitude=float(row.longitude),
            approved_observation_count=row.approved_count,
            last_activity_at=row.last_activity_at,
            distance_meters=float(row.distance_meters) if near is not None else None,
            categories=labels_by_location.get(row.id, []),
        )
        for row in rows
    ]


def _category_labels_by_location(
    db: Session, location_ids: list[UUID]
) -> dict[UUID, list[PublicCategoryLabel]]:
    """Active categories for many Locations in ONE query -- the same
    relevance floor and active-catalog filter as
    category_knowledge.get_location_coverage, minus the per-category
    knowledge rollup a card doesn't need. Ordered primary place_type first,
    then by relevance."""
    if not location_ids:
        return {}
    rows = db.execute(
        select(
            LocationCategoryAssignment.location_id,
            LocationCategory.slug,
            LocationCategory.kind,
            LocationCategory.display_name,
        )
        .join(LocationCategory, LocationCategory.id == LocationCategoryAssignment.category_id)
        .where(
            LocationCategoryAssignment.location_id.in_(location_ids),
            LocationCategoryAssignment.relevance >= settings.category_coverage_min_relevance,
            LocationCategory.active.is_(True),
            LocationCategory.slug.not_in(_NON_DESCRIPTIVE_CATEGORY_SLUGS),
        )
        .order_by(
            LocationCategoryAssignment.location_id,
            LocationCategoryAssignment.is_primary.desc(),
            LocationCategoryAssignment.relevance.desc(),
            LocationCategory.display_name,
        )
    ).all()
    labels: dict[UUID, list[PublicCategoryLabel]] = {}
    for location_id, slug, kind, display_name in rows:
        bucket = labels.setdefault(location_id, [])
        # 'area'/'trail' exist as BOTH a theme and a place_type (see
        # LocationCategory's docstring) -- one label per name on a card.
        if any(label.display_name == display_name for label in bucket):
            continue
        bucket.append(
            PublicCategoryLabel(slug=slug, kind=kind, display_name=display_name)
        )
    return labels


def _to_public_place_question(
    question: PlaceQuestion, answers: list[PublicPlaceQuestionAnswer]
) -> PublicPlaceQuestion:
    return PublicPlaceQuestion(
        place_question_id=question.id,
        question_text=question.question_text,
        context_note=question.context_note,
        answers=answers,
    )


def list_public_place_questions(db: Session, location_id: UUID) -> list[PublicPlaceQuestion]:
    """Active PlaceQuestions for this Location that have >= 1 APPROVED
    answer -- a question nobody has usefully answered yet is a guide-facing
    invitation, not public content, so it is omitted entirely. Reuses
    place_questions_service.list_place_questions for the active/ordering
    logic, never reimplements it.

    Answering a PlaceQuestion creates an ordinary Submission
    (submission_type='answer', source_place_question_id set) rather than a
    dedicated answer row -- see place_question_answers.py. 'Approved' here is
    SubmissionReview.status == 'approved' (the reward-eligibility gate on the
    Submission itself), NOT ObservationModeration -- most answers never
    produce an Observation, and even a category-driven answer's
    CategoryKnowledge-linked Observation is reviewed separately from whether
    the CONTRIBUTION itself was reward-worthy.

    One batched query for every candidate question's answers -- never one
    query per question.
    """
    questions = place_questions_service.list_place_questions(db, location_id)
    if not questions:
        return []

    question_ids = [q.id for q in questions]
    stmt = (
        select(Submission, Guide)
        .join(SubmissionReview, SubmissionReview.submission_id == Submission.id)
        .join(Guide, Guide.id == Submission.guide_id)
        .where(
            Submission.source_place_question_id.in_(question_ids),
            SubmissionReview.status == "approved",
        )
        .order_by(Submission.submitted_at.desc())
    )
    rows = db.execute(stmt).all()

    answers_by_question: dict[UUID, list[PublicPlaceQuestionAnswer]] = {}
    for submission, guide in rows:
        bucket = answers_by_question.setdefault(submission.source_place_question_id, [])
        if len(bucket) >= _ANSWERS_PER_QUESTION_LIMIT:
            continue
        bucket.append(
            PublicPlaceQuestionAnswer(
                submission_id=submission.id,
                answer_text=submission.raw_text or "",
                guide_name=guide.name,
                answered_at=submission.submitted_at,
            )
        )

    return [
        _to_public_place_question(question, answers_by_question[question.id])
        for question in questions
        if question.id in answers_by_question
    ]


def _bucket_route_stop_freshness(
    observed_at: datetime | None, evaluation_time: datetime
) -> tuple[KnowledgeState, float | None]:
    """PURE function, no DB access. A single LOCATION-level freshness bucket
    (has ANYTHING been reported here recently), distinct from
    evaluate_public_knowledge_state's per-KNOWLEDGE-TYPE windows and from
    CategoryKnowledge's per-fact freshness. Same fresh/aging/stale boundary
    math as knowledge_state._evaluate_one_type, against
    settings.route_stop_freshness_window_hours/route_stop_aging_threshold_hours
    instead of a per-type config row. 'missing' (age_hours=None) when
    observed_at is None."""
    if observed_at is None:
        return "missing", None

    freshness_expires_at = observed_at + timedelta(hours=settings.route_stop_freshness_window_hours)
    aging_expires_at = freshness_expires_at + timedelta(hours=settings.route_stop_aging_threshold_hours)
    age_hours = (evaluation_time - observed_at).total_seconds() / 3600.0

    if evaluation_time <= freshness_expires_at:
        return "fresh", age_hours
    if evaluation_time <= aging_expires_at:
        return "aging", age_hours
    return "stale", age_hours


def _latest_approved_observation_at_by_location(
    db: Session, location_ids: list[UUID]
) -> dict[UUID, datetime | None]:
    """Each given Location id's most recent APPROVED observation time within
    geographic_context_radius_meters of that Location's own point -- one
    grouped query (same outer-join-with-approval-folded-into-the-ON-clause
    technique as list_public_locations), never one query per location."""
    if not location_ids:
        return {}

    radius = settings.geographic_context_radius_meters
    locations_subq = (
        select(Location.id, Location.geog).where(Location.id.in_(location_ids)).subquery()
    )
    approved_activity = case(
        (ObservationModeration.observation_id.isnot(None), Observation.observed_at),
        else_=None,
    )
    stmt = (
        select(locations_subq.c.id, func.max(approved_activity).label("last_observed_at"))
        .select_from(locations_subq)
        .outerjoin(
            Observation,
            (Observation.geog.isnot(None))
            & (func.ST_DWithin(Observation.geog, locations_subq.c.geog, radius)),
        )
        .outerjoin(
            ObservationModeration,
            (ObservationModeration.observation_id == Observation.id)
            & (ObservationModeration.status == "approved"),
        )
        .group_by(locations_subq.c.id)
    )
    rows = db.execute(stmt).all()
    return {row.id: row.last_observed_at for row in rows}


def get_public_route_for_location(
    db: Session, location_id: UUID, evaluation_time: datetime
) -> PublicRoute | None:
    """None when this Location is not a stop on any seeded Route (the
    overwhelming majority of Locations). Otherwise the WHOLE route (every
    stop, not just this Location's own), ordered by sequence_order, each
    stop's status from a single batched freshness lookup -- never one query
    per stop."""
    route_id = db.execute(
        select(RouteStop.route_id).where(RouteStop.location_id == location_id)
    ).scalars().first()
    if route_id is None:
        return None

    route = db.get(Route, route_id)
    if route is None:
        return None

    rows = db.execute(
        select(RouteStop, Location)
        .join(Location, Location.id == RouteStop.location_id)
        .where(RouteStop.route_id == route_id)
        .order_by(RouteStop.sequence_order)
    ).all()
    if not rows:
        return None

    last_observed_by_location = _latest_approved_observation_at_by_location(
        db, [location.id for _stop, location in rows]
    )

    stops: list[PublicRouteStop] = []
    for stop, location in rows:
        last_observed_at = last_observed_by_location.get(location.id)
        status, age_hours = _bucket_route_stop_freshness(last_observed_at, evaluation_time)
        stops.append(
            PublicRouteStop(
                route_stop_id=stop.id,
                location_id=location.id,
                name=location.name,
                sequence_order=stop.sequence_order,
                stop_label=stop.stop_label,
                elevation_meters=stop.elevation_meters,
                latitude=float(location.latitude),
                longitude=float(location.longitude),
                status=status,
                last_observed_at=last_observed_at,
                age_hours=age_hours,
            )
        )

    return PublicRoute(
        route_id=route.id, slug=route.slug, name=route.name, description=route.description, stops=stops
    )


def list_public_location_categories(
    db: Session, location_id: UUID, evaluation_time: datetime
) -> list[PublicLocationCategory]:
    """This Location's active categories for a public reader. Thin mapper
    over category_knowledge.get_location_coverage -- the SAME relevance floor,
    active-catalog filter, relevance ordering and derived coverage state the
    guide app and question generation use; nothing is re-decided here.

    Two public-only reductions, both about trust:
      - only VERIFIED, active knowledge items are included (a pending item
        is "known about, not yet trusted" and must never read as fact);
      - the catalog's catch-all 'other' category is dropped -- it says
        nothing about a place a traveller could use.
    """
    coverage = category_knowledge_service.get_location_coverage(
        db, location_id, evaluation_time=evaluation_time
    )
    categories: list[PublicLocationCategory] = []
    for cov in coverage:
        if cov.slug in _NON_DESCRIPTIVE_CATEGORY_SLUGS:
            continue
        verified = sorted(
            (i for i in cov.items if i.active and category_knowledge_service.is_verified(i)),
            key=lambda i: i.last_verified_at,
            reverse=True,
        )
        categories.append(
            PublicLocationCategory(
                slug=cov.slug,
                kind=cov.kind,
                display_name=cov.display_name,
                relevance=cov.relevance,
                is_primary=cov.is_primary,
                state=cov.state,
                verified_knowledge=[
                    PublicVerifiedKnowledge(
                        knowledge_id=item.id,
                        knowledge_text=item.knowledge_text,
                        last_verified_at=item.last_verified_at,
                        fresh=category_knowledge_service.is_fresh(item, evaluation_time),
                    )
                    for item in verified
                ],
            )
        )
    return categories


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
    popular_questions = list_public_place_questions(db, location_id)
    route = get_public_route_for_location(db, location_id, evaluation_time)
    categories = list_public_location_categories(db, location_id, evaluation_time)
    nearby = list_public_locations(db, limit=settings.public_nearby_limit, near=location)

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
        research_summary=place_summary_service.to_read(
            place_summary_service.get_summary(db, location.id)
        ),
        popular_questions=popular_questions,
        route=route,
        categories=categories,
        nearby=nearby,
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
        _to_public_observation(db, obs, kt, sub, guide, tr, cat) for obs, kt, sub, guide, tr, cat in obs_rows
    ]

    return PublicSearchResult(
        query=q, locations=matched_locations, observations=matched_observations
    )
