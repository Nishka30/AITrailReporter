"""Knowledge Freshness/Staleness/Gap Detection engine (Step 10) -- deterministic,
no LLM calls. Answers: "for this geographic point and point in time, for each
active knowledge type, what is the current knowledge state?"
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.geo import make_point
from app.db.models.knowledge_type_config import KnowledgeTypeConfig
from app.db.models.observation import Observation
from app.schemas.knowledge_state import KnowledgeStateResult, KnowledgeStateSummary, KnowledgeTypeState
from app.services import knowledge_types as knowledge_type_service


class NaiveEvaluationTimeError(Exception):
    """Raised when an explicitly-supplied evaluation_time has no timezone --
    same rule SubmissionCreate.submitted_at already enforces elsewhere in this
    codebase, applied consistently here rather than silently assuming UTC."""


def resolve_evaluation_time(evaluation_time: datetime | None) -> datetime:
    """Defaults to the current server time (UTC) when not supplied, but the
    CORE service (evaluate_knowledge_state below) never calls datetime.now()
    itself -- every caller, including tests, must pass an explicit,
    timezone-aware evaluation_time so the exact same data can be evaluated at
    different points in time deterministically."""
    if evaluation_time is None:
        return datetime.now(timezone.utc)
    if evaluation_time.tzinfo is None or evaluation_time.tzinfo.utcoffset(evaluation_time) is None:
        raise NaiveEvaluationTimeError()
    return evaluation_time


def _find_latest_relevant_observation(
    db: Session, knowledge_type_id, target_point, radius_meters: float
) -> tuple[Observation | None, float | None]:
    """The latest (by observed_at) Observation of this knowledge type that is
    geographically relevant -- i.e. within THIS knowledge type's own configured
    radius, via PostGIS ST_DWithin (never Python/Haversine distance math).
    Observations with no geog at all (never given a resolvable coordinate, see
    Step 9) can never match ST_DWithin and are correctly never selected here.
    """
    distance = func.ST_Distance(Observation.geog, target_point).label("distance_meters")
    stmt = (
        select(Observation, distance)
        .where(
            Observation.knowledge_type_id == knowledge_type_id,
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


def _evaluate_one_type(
    kt: KnowledgeTypeConfig,
    observation: Observation | None,
    distance_meters: float | None,
    evaluation_time: datetime,
) -> KnowledgeTypeState:
    if observation is None:
        return KnowledgeTypeState(
            knowledge_type_id=kt.id,
            knowledge_type=kt.knowledge_type,
            display_name=kt.display_name,
            state="missing",
            latest_observation_id=None,
            observed_at=None,
            age_hours=None,
            distance_meters=None,
            freshness_window_hours=kt.freshness_window_hours,
            freshness_expires_at=None,
            aging_threshold_hours=kt.aging_threshold_hours,
            aging_expires_at=None,
            geographic_relevance_radius_meters=kt.geographic_relevance_radius_meters,
            safety_critical=kt.safety_critical,
            default_priority=kt.default_priority,
            severity_hours=0.0,
        )

    freshness_expires_at = observation.observed_at + timedelta(hours=kt.freshness_window_hours)
    # aging_expires_at is computed whenever aging_threshold_hours is configured
    # at all -- INCLUDING the exact value 0. A zero-width window still yields a
    # real, well-defined instant (equal to freshness_expires_at itself); the
    # three-way boundary comparison below naturally falls through fresh ->
    # stale for that case without any special-casing, because
    # "evaluation_time <= aging_expires_at" can only be true at the SAME
    # instant the fresh check above it already caught. Only a NULL
    # aging_threshold_hours (no aging period configured at all) leaves
    # aging_expires_at as None.
    aging_expires_at = (
        freshness_expires_at + timedelta(hours=kt.aging_threshold_hours)
        if kt.aging_threshold_hours is not None
        else None
    )

    # Boundary rules (explicit, per this step's spec), evaluated in order:
    #   1. evaluation_time <= freshness_expires_at             -> fresh
    #      (exactly AT the freshness edge is still fully fresh)
    #   2. aging_expires_at is not None and
    #      evaluation_time <= aging_expires_at                 -> aging
    #      (exactly AT the aging edge is still aging; unreachable when
    #      aging_expires_at == freshness_expires_at, i.e. aging_threshold_hours
    #      == 0, since that instant was already claimed by check 1)
    #   3. otherwise                                            -> stale
    #      (immediately after whichever edge applies -- the aging edge if one
    #      exists, otherwise the freshness edge directly)
    if evaluation_time <= freshness_expires_at:
        state: str = "fresh"
    elif aging_expires_at is not None and evaluation_time <= aging_expires_at:
        state = "aging"
    else:
        state = "stale"

    age_hours = (evaluation_time - observation.observed_at).total_seconds() / 3600.0

    # severity_hours: how far PAST the relevant expiry boundary evaluation_time
    # is, for the state just computed. Never negative -- clamped defensively
    # even though the boundary rules above already guarantee non-negativity
    # for 'aging'/'stale' by construction.
    if state == "aging":
        severity_hours = max(
            (evaluation_time - freshness_expires_at).total_seconds() / 3600.0, 0.0
        )
    elif state == "stale":
        stale_baseline = aging_expires_at if aging_expires_at is not None else freshness_expires_at
        severity_hours = max((evaluation_time - stale_baseline).total_seconds() / 3600.0, 0.0)
    else:
        severity_hours = 0.0

    return KnowledgeTypeState(
        knowledge_type_id=kt.id,
        knowledge_type=kt.knowledge_type,
        display_name=kt.display_name,
        state=state,
        latest_observation_id=observation.id,
        observed_at=observation.observed_at,
        age_hours=age_hours,
        distance_meters=distance_meters,
        freshness_window_hours=kt.freshness_window_hours,
        freshness_expires_at=freshness_expires_at,
        aging_threshold_hours=kt.aging_threshold_hours,
        aging_expires_at=aging_expires_at,
        geographic_relevance_radius_meters=kt.geographic_relevance_radius_meters,
        safety_critical=kt.safety_critical,
        default_priority=kt.default_priority,
        severity_hours=severity_hours,
    )


def evaluate_knowledge_state(
    db: Session, latitude: float, longitude: float, evaluation_time: datetime
) -> KnowledgeStateResult:
    """Core, deterministic knowledge-state evaluation for one coordinate at one
    instant. `evaluation_time` is REQUIRED and must be timezone-aware (use
    resolve_evaluation_time() at the API boundary to default/validate it) --
    this service never hides time behind an internal now() call, so the exact
    same observation data can be replayed at different evaluation times
    (needed for both testing and, later, "what did we know as of X").

    For every ACTIVE KnowledgeTypeConfig (inactive types never appear in the
    result): finds the latest geographically-relevant Observation using THAT
    type's own freshness window, aging threshold, and radius, then classifies
    it missing / fresh / aging / stale (Step 14 adds 'aging' -- see
    _evaluate_one_type for the exact boundary rules). Confidence is
    deliberately NOT used to filter or weight anything here -- there is no
    existing configured confidence policy to apply, and this step must not
    silently exclude data based on an invented threshold.
    """
    target_point = make_point(latitude, longitude)
    active_types = knowledge_type_service.get_active_knowledge_types(db)

    type_states = [
        _evaluate_one_type(
            kt,
            *_find_latest_relevant_observation(
                db, kt.id, target_point, kt.geographic_relevance_radius_meters
            ),
            evaluation_time,
        )
        for kt in active_types
    ]

    fresh_count = sum(1 for t in type_states if t.state == "fresh")
    aging_count = sum(1 for t in type_states if t.state == "aging")
    stale_count = sum(1 for t in type_states if t.state == "stale")
    missing_count = sum(1 for t in type_states if t.state == "missing")
    # A gap is anything that is not fully 'fresh' (Step 14, Part D) --
    # 'aging' counts as a gap alongside 'stale'/'missing', even though it is
    # ranked less urgently than either (see knowledge_decisions.py).
    gaps = [t for t in type_states if t.state != "fresh"]

    summary = KnowledgeStateSummary(
        total_active_types=len(type_states),
        fresh_count=fresh_count,
        aging_count=aging_count,
        stale_count=stale_count,
        missing_count=missing_count,
        gap_count=aging_count + stale_count + missing_count,
    )

    return KnowledgeStateResult(
        latitude=latitude,
        longitude=longitude,
        evaluation_time=evaluation_time,
        knowledge_types=type_states,
        summary=summary,
        gaps=gaps,
    )
