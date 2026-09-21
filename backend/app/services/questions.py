"""Question generation + assignment orchestration (Step 12). Takes a ranked
knowledge gap (Step 10 + Step 11, reused unmodified) and turns it into a
persisted, natural-language question for a trek guide -- deterministic
decision-making stays entirely in Step 10/11; this module only adds LLM
phrasing + persistence + assignment on top.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.geo import make_point
from app.db.models.guide import Guide
from app.db.models.knowledge_type_config import KnowledgeTypeConfig
from app.db.models.location import Location
from app.db.models.question import Question
from app.db.models.question_assignment import QuestionAssignment
from app.schemas.knowledge_decision import RankedGap
from app.schemas.question import QuestionAssignmentRead, QuestionRead
from app.schemas.question_answer import QuestionAnswerRead
from app.services import geographic_context as geographic_context_service
from app.services import knowledge_decisions as knowledge_decision_service
from app.services import knowledge_types as knowledge_type_service
from app.services import question_answers as question_answer_service
from app.services import rewards as reward_service
from app.services import submission_review as submission_review_service
from app.services.question_generation.anthropic_provider import (
    QuestionGenerationProviderError,
    generate_question_text,
)
from app.services.question_generation.validation import (
    InvalidQuestionOutputError,
    validate_question_output,
)

# Mirrors knowledge_decisions.py's _GAP_STATE_URGENCY_RANK -- this module
# does not recompute urgency, it just re-applies the SAME precedence to
# already-generated Question rows instead of live-computed gaps. Kept as a
# separate constant (not imported) because it indexes a different thing --
# Question.gap_state (a persisted snapshot string), not KnowledgeTypeState.
_GAP_STATE_URGENCY_RANK: dict[str, int] = {"missing": 0, "stale": 1, "aging": 2}


class LocationNotFoundError(Exception):
    def __init__(self, location_id: UUID):
        self.location_id = location_id
        super().__init__(f"Location {location_id} not found")

_GAP_RESOLVED_MESSAGE = (
    "The underlying knowledge gap was resolved (became fresh, or is no longer "
    "an active gap) before question generation completed. Discarded rather "
    "than persisting or assigning an obsolete question. Retry if this is "
    "still relevant."
)


class UnknownKnowledgeTypeError(Exception):
    """Raised when the requested knowledge_type doesn't match any active
    KnowledgeTypeConfig row."""

    def __init__(self, knowledge_type: str):
        self.knowledge_type = knowledge_type
        super().__init__(f"Unknown or inactive knowledge_type: {knowledge_type!r}")


class GapNotFoundError(Exception):
    """Raised when creating a BRAND NEW question and the requested
    knowledge_type is not currently a gap (missing/aging/stale, Step 14) at
    the given coordinate/time -- it's either fresh, or there's nothing there
    at all."""

    def __init__(self, knowledge_type: str):
        self.knowledge_type = knowledge_type
        super().__init__(f"{knowledge_type!r} is not currently a knowledge gap at this location.")


class QuestionConflictError(Exception):
    """Raised when a client_request_id is reused with a different
    knowledge_type/location than the original request it was first used for."""

    def __init__(self, existing: Question):
        self.existing = existing
        super().__init__(
            f"client_request_id {existing.client_request_id!r} was already used "
            "with a different knowledge_type/location"
        )


def get_question(db: Session, question_id: UUID) -> Question | None:
    return db.get(Question, question_id)


def get_question_by_client_request_id(db: Session, client_request_id: str) -> Question | None:
    stmt = select(Question).where(Question.client_request_id == client_request_id)
    return db.execute(stmt).scalar_one_or_none()


def _get_current_assignment(db: Session, question_id: UUID) -> QuestionAssignment | None:
    stmt = (
        select(QuestionAssignment)
        .where(QuestionAssignment.question_id == question_id)
        .order_by(QuestionAssignment.assigned_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def build_question_read(db: Session, question: Question) -> QuestionRead:
    knowledge_type = db.get(KnowledgeTypeConfig, question.knowledge_type_id)
    assignment_row = _get_current_assignment(db, question.id)
    assignment = None
    if assignment_row is not None:
        guide = db.get(Guide, assignment_row.guide_id)
        assignment = QuestionAssignmentRead(
            id=assignment_row.id,
            guide_id=assignment_row.guide_id,
            guide_name=guide.name if guide is not None else "",
            status=assignment_row.status,
            assigned_at=assignment_row.assigned_at,
            answered_at=assignment_row.answered_at,
        )
    answer_row = question_answer_service.get_latest_answer_for_question(db, question.id)
    answer = None
    if answer_row is not None:
        answer = QuestionAnswerRead.model_validate(answer_row)
        # Admin-approval gate (Step 19): attach the review decision, if any,
        # so the app can distinguish "pending admin approval" from "approved,
        # you earned N points" from "not approved: <reason>" without a second
        # request. review is None only for an answer that predates this
        # feature (paid immediately, under the old behavior).
        review = submission_review_service.get_review(db, answer_row.submission_id)
        if review is not None:
            answer = answer.model_copy(
                update={
                    "review_status": review.status,
                    "rejection_reason": review.rejection_reason,
                    "rejection_note": review.rejection_note,
                    "reward_points_awarded": review.reward_points_awarded,
                }
            )
    return QuestionRead(
        id=question.id,
        knowledge_type_id=question.knowledge_type_id,
        knowledge_type=knowledge_type.knowledge_type if knowledge_type else "",
        display_name=knowledge_type.display_name if knowledge_type else "",
        gap_state=question.gap_state,
        target_latitude=float(question.target_latitude),
        target_longitude=float(question.target_longitude),
        nearest_known_place_name=question.nearest_known_place_name,
        nearest_known_place_distance_meters=question.nearest_known_place_distance_meters,
        safety_critical=question.safety_critical,
        default_priority=question.default_priority,
        staleness_severity_hours=question.staleness_severity_hours,
        gap_rank=question.gap_rank,
        question_text=question.question_text,
        short_context=question.short_context,
        status=question.status,
        error_message=question.error_message,
        attempt_count=question.attempt_count,
        created_at=question.created_at,
        updated_at=question.updated_at,
        assignment=assignment,
        answer=answer,
        # Resolved live from reward_rules (Step 18) rather than snapshotted on
        # the Question row: this is "what answering it is worth right now", and
        # a rule change should be reflected immediately in what the app offers.
        # What was actually PAID is separately immutable in reward_ledger, so
        # changing a rule never rewrites history.
        reward_points=reward_service.resolve_points(
            db, question_answer_service.reward_rule_key_for_question(db, question)
        ),
    )


def list_questions_for_guide(
    db: Session, guide_id: UUID, status: str | None
) -> list[Question]:
    """Questions currently assigned to a guide, most recently assigned first.
    Joins through QuestionAssignment (never a guide_id column on Question
    itself -- there isn't one, see app/db/models/question_assignment.py).
    `status` filters on the ASSIGNMENT's status (e.g. 'assigned'), not the
    question's own generation status."""
    stmt = (
        select(Question)
        .join(QuestionAssignment, QuestionAssignment.question_id == Question.id)
        .where(QuestionAssignment.guide_id == guide_id)
    )
    if status is not None:
        stmt = stmt.where(QuestionAssignment.status == status)
    stmt = stmt.order_by(QuestionAssignment.assigned_at.desc())
    return list(db.execute(stmt).scalars().all())


def _question_sort_key(question: Question, distance_meters: float) -> tuple:
    """Mirrors knowledge_decisions.py::_gap_sort_key's precedence (safety
    first, then gap-state urgency, then priority, then severity) over
    already-generated Question rows instead of live gaps, plus distance as a
    final tiebreaker -- proximity is what makes this list exist at all, but
    it only ever breaks ties among equally-urgent questions, never overrides
    urgency itself."""
    return (
        not question.safety_critical,
        _GAP_STATE_URGENCY_RANK.get(question.gap_state, 99),
        -question.default_priority,
        -question.staleness_severity_hours,
        distance_meters,
    )


def list_geographically_relevant_questions(
    db: Session, location_id: UUID, limit: int = 20
) -> list[QuestionRead]:
    """Existing, already-generated questions near a known Location, most
    urgent/stale first -- the read half of the proximity feature. Never
    generates anything (no LLM call, ever, from this function) and never
    recomputes knowledge state live: it reuses exactly the ranking snapshot
    (safety_critical/gap_state/default_priority/staleness_severity_hours)
    Step 11 already wrote onto each Question row at generation time.

    Anchored on the CALLER'S already-resolved Location (its id), not a raw
    lat/lon and not a fan-out across every nearby known place -- the caller
    (mobile's selectedPlace) already knows which single place it means, so
    there is no second geographic search here and no risk of flooding the
    user with every place's questions at once.

    Radius is read PER-QUESTION from that question's own knowledge type's
    KnowledgeTypeConfig.geographic_relevance_radius_meters (never a
    hardcoded constant) -- one query total, via a JOIN, not one query per
    candidate question.

    Excludes questions whose current assignment is already 'completed' (the
    guide-facing "Answered" list already covers those) -- everything else
    (unassigned, assigned-but-not-yet-answered, or cancelled) is eligible,
    since claiming happens separately (see question_answers.py::claim_question)
    only when a guide actually opens one to answer it.
    """
    location = db.get(Location, location_id)
    if location is None:
        raise LocationNotFoundError(location_id)

    point = make_point(float(location.latitude), float(location.longitude))
    distance = func.ST_Distance(Question.geog, point).label("distance_meters")

    latest_assignment = (
        select(
            QuestionAssignment.question_id,
            QuestionAssignment.status,
            func.row_number()
            .over(
                partition_by=QuestionAssignment.question_id,
                order_by=QuestionAssignment.assigned_at.desc(),
            )
            .label("rn"),
        )
        .subquery()
    )
    current_status = (
        select(latest_assignment.c.status)
        .where(latest_assignment.c.question_id == Question.id, latest_assignment.c.rn == 1)
        .correlate(Question)
        .scalar_subquery()
    )

    stmt = (
        select(Question, distance)
        .join(KnowledgeTypeConfig, KnowledgeTypeConfig.id == Question.knowledge_type_id)
        .where(
            Question.status == "generated",
            Question.geog.isnot(None),
            func.ST_DWithin(Question.geog, point, KnowledgeTypeConfig.geographic_relevance_radius_meters),
            or_(current_status.is_(None), current_status != "completed"),
        )
    )
    rows = db.execute(stmt).all()
    rows.sort(key=lambda row: _question_sort_key(row[0], float(row[1])))
    return [build_question_read(db, question) for question, _distance in rows[:limit]]


def _ensure_compatible(existing: Question, knowledge_type_id, latitude: float, longitude: float) -> None:
    if (
        existing.knowledge_type_id != knowledge_type_id
        or float(existing.target_latitude) != latitude
        or float(existing.target_longitude) != longitude
    ):
        raise QuestionConflictError(existing)


def _find_ranked_gap(
    ranked_gaps: list[RankedGap], knowledge_type_name: str
) -> RankedGap | None:
    return next((g for g in ranked_gaps if g.knowledge_type == knowledge_type_name), None)


def _get_or_create_question_row(
    db: Session,
    client_request_id: str | None,
    knowledge_type: KnowledgeTypeConfig,
    knowledge_type_name: str,
    latitude: float,
    longitude: float,
    evaluation_time: datetime,
) -> Question:
    """Get-or-create, locked -- same shape as
    app/services/extractions.py::_get_or_create_extraction_row. Unlike
    Transcription/Extraction (keyed by a pre-existing submission_id), a
    "gap" is not itself a persisted entity, so there is nothing to look up
    without a client_request_id -- creating a brand-new row REQUIRES a fresh,
    real gap to exist right now (raises GapNotFoundError otherwise); replaying
    an existing client_request_id never re-checks gap existence at this stage
    (that would break idempotent replay of an already-succeeded request after
    the world moved on) -- see generate_question's own pre-claim check for
    where retries are re-verified instead.
    """
    if client_request_id is not None:
        stmt = (
            select(Question)
            .where(Question.client_request_id == client_request_id)
            .with_for_update()
        )
        existing = db.execute(stmt).scalar_one_or_none()
        if existing is not None:
            _ensure_compatible(existing, knowledge_type.id, latitude, longitude)
            return existing

    decision = knowledge_decision_service.evaluate_knowledge_decision(
        db, latitude, longitude, evaluation_time
    )
    gap = _find_ranked_gap(decision.ranked_gaps, knowledge_type_name)
    if gap is None:
        raise GapNotFoundError(knowledge_type_name)

    nearest_place = geographic_context_service.resolve_geographic_context(
        db, latitude, longitude
    ).nearest_known_place

    question = Question(
        client_request_id=client_request_id,
        knowledge_type_id=knowledge_type.id,
        gap_state=gap.state,
        target_latitude=latitude,
        target_longitude=longitude,
        geog=make_point(latitude, longitude),
        nearest_known_place_name=nearest_place.name if nearest_place else None,
        nearest_known_place_distance_meters=(
            nearest_place.distance_meters if nearest_place else None
        ),
        safety_critical=gap.safety_critical,
        default_priority=gap.default_priority,
        staleness_severity_hours=gap.staleness_severity_hours,
        gap_rank=gap.rank,
        status="pending",
        provider="anthropic",
    )
    db.add(question)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        if client_request_id is None:
            raise
        stmt = (
            select(Question)
            .where(Question.client_request_id == client_request_id)
            .with_for_update()
        )
        existing = db.execute(stmt).scalar_one_or_none()
        if existing is None:
            raise
        _ensure_compatible(existing, knowledge_type.id, latitude, longitude)
        return existing
    return question


def _mark_failed(db: Session, question: Question, message: str) -> Question:
    question.status = "failed"
    question.error_message = message
    db.commit()
    db.refresh(question)
    return question


def generate_question(
    db: Session,
    latitude: float,
    longitude: float,
    knowledge_type_name: str,
    evaluation_time: datetime,
    client_request_id: str | None,
) -> tuple[Question, str]:
    """Runs one question-generation attempt for a ranked knowledge gap, or
    reports the current state without calling the provider again if there is
    nothing new to do.

    Returns (question, outcome), outcome one of:
      'generated'  - a validated question is now persisted (this attempt or a
                     previous one), with an assignment if a guide was selected
      'failed'     - this attempt failed; question.error_message is set
      'processing' - another request is already processing this question; the
                     provider was NOT called again by this call

    Raises UnknownKnowledgeTypeError, GapNotFoundError, or
    QuestionConflictError -- see each exception's docstring.

    Concurrency: the same "claim, then act, then finalize" pattern as
    start_transcription/start_extraction -- the Question row is locked
    (SELECT ... FOR UPDATE, via _get_or_create_question_row) only for the
    brief claim step, never across the slow LLM call.

    Revalidation (Part I of this step's spec): knowledge state is computed
    LIVE (Step 10) and can change while this request is in flight. The gap is
    checked once more, immediately before claiming (a cheap guard against
    spending an LLM call on an already-resolved retry), and AGAIN immediately
    after the LLM call returns, right before persisting/assigning -- using the
    freshly re-evaluated selected_guide too, not the pre-call one, since a
    guide could also have moved during the call. This narrows the race window
    from "the whole LLM call" down to "the final read-then-write," but does
    NOT eliminate it -- no database transaction is held open across the
    external Anthropic call (per this step's explicit constraint), so a
    third observation arriving in the few milliseconds between the
    revalidation read and the final commit is a real, accepted, un-closed
    race. This is an honest trade-off, not a claimed guarantee.
    """
    knowledge_type = knowledge_type_service.get_active_knowledge_type_by_name(
        db, knowledge_type_name
    )
    if knowledge_type is None:
        raise UnknownKnowledgeTypeError(knowledge_type_name)

    question = _get_or_create_question_row(
        db, client_request_id, knowledge_type, knowledge_type_name, latitude, longitude, evaluation_time
    )

    if question.status == "generated":
        db.commit()
        return question, "generated"
    if question.status == "processing":
        db.commit()
        return question, "processing"

    # 'pending' or 'failed' -> re-verify the gap still exists before spending
    # an LLM call on it.
    decision = knowledge_decision_service.evaluate_knowledge_decision(
        db, latitude, longitude, evaluation_time
    )
    gap = _find_ranked_gap(decision.ranked_gaps, knowledge_type_name)
    if gap is None:
        return _mark_failed(db, question, _GAP_RESOLVED_MESSAGE), "failed"

    # Claim this attempt. Commit here releases the row lock immediately,
    # BEFORE the slow LLM call below.
    question.status = "processing"
    question.attempt_count += 1
    question.started_at = datetime.now(timezone.utc)
    question.error_message = None
    db.commit()
    db.refresh(question)

    try:
        raw_output = generate_question_text(
            gap.display_name,
            gap.state,
            gap.staleness_severity_hours,
            question.nearest_known_place_name,
            question.nearest_known_place_distance_meters,
        )
    except QuestionGenerationProviderError as exc:
        return _mark_failed(db, question, exc.message), "failed"

    try:
        validated = validate_question_output(raw_output)
    except InvalidQuestionOutputError as exc:
        return _mark_failed(db, question, exc.message), "failed"

    # Revalidation: re-check right before persisting/assigning.
    revalidation = knowledge_decision_service.evaluate_knowledge_decision(
        db, latitude, longitude, evaluation_time
    )
    revalidated_gap = _find_ranked_gap(revalidation.ranked_gaps, knowledge_type_name)
    if revalidated_gap is None:
        return _mark_failed(db, question, _GAP_RESOLVED_MESSAGE), "failed"

    question.question_text = validated.question_text
    question.short_context = validated.short_context
    question.status = "generated"
    question.model = settings.anthropic_model
    question.completed_at = datetime.now(timezone.utc)
    question.error_message = None

    # Part E, step 5: if no guide is currently relevant, persist the question
    # UNASSIGNED rather than fabricating a guide or discarding the (real, valid)
    # generated question -- it remains useful, queryable knowledge-gap output,
    # and a future step can retry assignment as guides move or new GPS data
    # arrives (exactly the follow-up Step 11 already anticipated).
    if revalidated_gap.selected_guide is not None:
        db.add(
            QuestionAssignment(
                question_id=question.id,
                guide_id=revalidated_gap.selected_guide.guide_id,
                status="assigned",
                assigned_at=datetime.now(timezone.utc),
            )
        )

    db.commit()
    db.refresh(question)
    return question, "generated"
