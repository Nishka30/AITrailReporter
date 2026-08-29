import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.geo import make_point
from app.db.models.extraction import Extraction
from app.db.models.observation import Observation
from app.db.models.submission import Submission
from app.schemas.extraction import ExtractionRead
from app.schemas.observation import ObservationRead
from app.services import geographic_context as geographic_context_service
from app.services import guide_locations as guide_location_service
from app.services import knowledge_types as knowledge_type_service
from app.services import observation_moderation as observation_moderation_service
from app.services import observations as observation_service
from app.services import source_text as source_text_service
from app.services.extraction.anthropic_provider import ExtractionProviderError, extract_observations
from app.services.extraction.validation import (
    InvalidExtractionOutputError,
    ValidatedObservation,
    validate_llm_output,
)

logger = logging.getLogger(__name__)


def get_extraction_by_submission_id(db: Session, submission_id: UUID) -> Extraction | None:
    stmt = select(Extraction).where(Extraction.submission_id == submission_id)
    return db.execute(stmt).scalar_one_or_none()


def build_extraction_read(db: Session, extraction: Extraction) -> ExtractionRead:
    """Assembles the API response for one Extraction, joining in its persisted
    observations (only meaningful once status == 'completed'; empty list
    otherwise, including 'failed' -- a failed attempt never persists partial
    observations, see start_extraction)."""
    observations = [
        ObservationRead(
            id=obs.id,
            submission_id=obs.submission_id,
            guide_id=obs.guide_id,
            knowledge_type=knowledge_type,
            latitude=float(obs.latitude) if obs.latitude is not None else None,
            longitude=float(obs.longitude) if obs.longitude is not None else None,
            value=obs.value,
            confidence=float(obs.confidence) if obs.confidence is not None else None,
            evidence=obs.evidence,
            observed_at=obs.observed_at,
            created_at=obs.created_at,
        )
        for obs, knowledge_type in observation_service.list_observations_for_submission(
            db, extraction.submission_id
        )
    ]
    return ExtractionRead(
        id=extraction.id,
        submission_id=extraction.submission_id,
        status=extraction.status,
        provider=extraction.provider,
        model=extraction.model,
        error_message=extraction.error_message,
        attempt_count=extraction.attempt_count,
        started_at=extraction.started_at,
        completed_at=extraction.completed_at,
        created_at=extraction.created_at,
        updated_at=extraction.updated_at,
        observations=observations,
    )


def _get_or_create_extraction_row(db: Session, submission_id: UUID) -> Extraction:
    """Get-or-create, locked. Unlike Transcription (pre-created eagerly when
    audio is attached, so this race can't happen there), Extraction is created
    lazily on the first POST .../extract -- a genuine concurrent "first ever
    trigger" race is possible, so creation itself needs the same
    IntegrityError-catch-and-refetch pattern used by create_or_get_submission
    etc., not just the claim step below."""
    stmt = select(Extraction).where(Extraction.submission_id == submission_id).with_for_update()
    extraction = db.execute(stmt).scalar_one_or_none()
    if extraction is not None:
        return extraction

    extraction = Extraction(submission_id=submission_id, status="pending", provider="anthropic")
    db.add(extraction)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        stmt = select(Extraction).where(Extraction.submission_id == submission_id).with_for_update()
        extraction = db.execute(stmt).scalar_one_or_none()
        if extraction is None:
            raise
    return extraction


def _mark_failed(db: Session, extraction: Extraction, message: str) -> Extraction:
    extraction.status = "failed"
    extraction.error_message = message
    db.commit()
    db.refresh(extraction)
    return extraction


# date_source values that mean "occurred_at is a genuinely known, independent
# moment in time" -- established from the content itself (EXIF) or a human who
# actually knows (user_entered/inferred) -- as opposed to "device"/"unknown",
# which mean occurred_at is just standing in for "approximately now" (see
# submissions.create_or_get_submission's defaulting). Only the former justifies
# looking for a GuideLocation sample that arrived AFTER occurred_at; the latter
# preserves this function's original backward-only behaviour exactly, so every
# existing live-capture flow is completely unaffected by this change.
_INDEPENDENT_DATE_SOURCES = ("exif", "user_entered", "inferred")


def _resolve_observation_coordinates(
    db: Session, submission: Submission
) -> tuple[float, float, str | None, str | None] | None:
    """The coordinate to attach to this submission's observations, or None if
    nothing is known -- never fabricated. Returns (latitude, longitude,
    location_source, location_evidence); the latter two are copied onto the
    Observation being built so provenance survives past this one function.

    Three tiers, in order:

    1. The submission's OWN latitude/longitude, if the client supplied them
       (live GPS, photo EXIF GPS, or a user-selected place -- whichever it is,
       it is already recorded on submission.location_source and trusted as-is).

    2. HISTORICAL INFERENCE, only when occurred_at is a genuinely independent,
       known moment (see _INDEPENDENT_DATE_SOURCES) rather than a stand-in for
       "now": the guide's own GuideLocation sample closest in time to
       occurred_at, from either side, but ONLY within
       settings.historical_location_max_gap_hours. This is written back onto
       the Submission itself (not just returned) -- a memory/old-photo upload
       that gets a location this way should show that provenance on the row
       from then on, not just on the Observation it happened to produce first.

    3. The old, exact pre-existing behaviour for everything else (a live
       report with no coordinate of its own): the guide's latest known
       GuideLocation AT OR BEFORE submitted_at, never after -- a ping recorded
       later might reflect the guide having already moved on, which would be
       wrong for "where were they when they made THIS report right now".
    """
    if submission.latitude is not None and submission.longitude is not None:
        return (
            float(submission.latitude),
            float(submission.longitude),
            submission.location_source,
            submission.location_evidence,
        )

    if submission.date_source in _INDEPENDENT_DATE_SOURCES and submission.occurred_at is not None:
        match = guide_location_service.find_nearest_location_in_time(
            db,
            submission.guide_id,
            submission.occurred_at,
            max_gap=timedelta(hours=settings.historical_location_max_gap_hours),
        )
        if match is not None:
            guide_location, gap = match
            direction = "before" if guide_location.recorded_at <= submission.occurred_at else "after"
            evidence = (
                f"Matched to a recorded GPS sample {_format_gap(gap)} {direction} "
                "the estimated time this content is about."
            )
            # Written back onto the Submission itself, not just returned --
            # this is what makes the inference visible to Admin on the row
            # going forward, per "don't let extraction discard where the
            # observation came from". Committed together with the rest of
            # start_extraction's single final transaction.
            submission.latitude = guide_location.latitude
            submission.longitude = guide_location.longitude
            submission.location_source = "historical_inferred"
            submission.location_evidence = evidence
            return (
                float(guide_location.latitude),
                float(guide_location.longitude),
                "historical_inferred",
                evidence,
            )
        # No sample close enough in time -- stays honestly unresolved rather
        # than falling through to tier 3, which would silently use whatever
        # the guide's CURRENT/live location happens to be for content that is
        # explicitly about a different, known moment in the past.
        return None

    guide_location = guide_location_service.get_latest_location_at_or_before(
        db, submission.guide_id, submission.submitted_at
    )
    if guide_location is not None:
        # Not written back onto the Submission itself, unlike tier 2 above:
        # this path exists for "now"-ish content (no independently-known
        # occurred_at), so the coordinate genuinely IS "wherever the guide's
        # GPS last said they were" for THIS submission specifically, not a
        # durable fact worth persisting back onto the row the way an old
        # photo's inferred location is.
        return (
            float(guide_location.latitude),
            float(guide_location.longitude),
            "historical_inferred",
            "Matched to the guide's most recent recorded GPS sample at the time of this report.",
        )

    return None


def _format_gap(gap: timedelta) -> str:
    total_minutes = round(gap.total_seconds() / 60)
    if total_minutes < 60:
        return f"{total_minutes} min"
    hours = total_minutes / 60
    return f"{hours:.1f}h"


def start_extraction(db: Session, submission_id: UUID) -> tuple[Extraction, str]:
    """Runs one LLM extraction attempt for a submission's resolved source text,
    or reports the current state without calling the provider again if there is
    nothing new to do.

    Returns (extraction, outcome), outcome one of:
      'completed'  - validated observations are now persisted (this attempt or a
                     previous one; zero observations is a valid completed result)
      'failed'     - this attempt failed; extraction.error_message is set
      'processing' - another request is already processing this submission; the
                     provider was NOT called again by this call

    Raises LookupError if the submission doesn't exist, or a source_text.
    SourceTextError subclass if there is no usable text to extract from yet
    (mirrors app/services/transcriptions.py's precondition-error style).

    Concurrency: the same "claim, then act, then finalize" pattern as
    start_transcription in app/services/transcriptions.py -- the Extraction row
    is locked (SELECT ... FOR UPDATE) only for the brief claim step, never across
    the slow LLM network call. Whichever concurrent caller's claim commits first
    proceeds to call the provider; every other concurrent caller's SELECT FOR
    UPDATE blocks until that commit, then observes 'processing' (or 'completed')
    already set and returns without a second provider call or duplicate
    observations. Observations are inserted and the row is marked 'completed' in
    ONE final commit, so a crash between them can never leave partial
    observations behind for a 'failed' or still-'processing' row.
    """
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise LookupError(f"Submission {submission_id} not found")

    extraction = _get_or_create_extraction_row(db, submission_id)

    if extraction.status == "completed":
        db.commit()
        return extraction, "completed"
    if extraction.status == "processing":
        db.commit()
        return extraction, "processing"

    # 'pending' or 'failed' -> before claiming, make sure there is actually
    # something to extract from. Resolving source text never mutates anything,
    # so on failure we release the lock (commit with no changes) and re-raise --
    # the row is left exactly as it was, still retryable once source text exists.
    try:
        source_text = source_text_service.resolve_source_text(db, submission)
    except source_text_service.SourceTextError:
        db.commit()
        raise

    # Claim this attempt. Commit here releases the row lock immediately, BEFORE
    # the slow LLM call below.
    extraction.status = "processing"
    extraction.attempt_count += 1
    extraction.started_at = datetime.now(timezone.utc)
    extraction.error_message = None
    db.commit()
    db.refresh(extraction)

    allowed_types = knowledge_type_service.get_active_knowledge_types(db)
    if not allowed_types:
        return (
            _mark_failed(db, extraction, "No active knowledge types are configured on the server."),
            "failed",
        )

    resolved = _resolve_observation_coordinates(db, submission)
    coordinates = resolved[:2] if resolved is not None else None
    location_source = resolved[2] if resolved is not None else None
    location_evidence = resolved[3] if resolved is not None else None
    nearest_known_place = None
    if coordinates is not None:
        context = geographic_context_service.resolve_geographic_context(db, *coordinates)
        nearest_known_place = context.nearest_known_place

    try:
        raw_output = extract_observations(source_text, allowed_types, nearest_known_place)
    except ExtractionProviderError as exc:
        return _mark_failed(db, extraction, exc.message), "failed"

    try:
        validated_observations, validated_new_types = validate_llm_output(
            raw_output, allowed_types
        )
    except InvalidExtractionOutputError as exc:
        return _mark_failed(db, extraction, exc.message), "failed"

    # Step 16 (Case B): resolve each validated proposal into a real
    # KnowledgeTypeConfig row FIRST, then treat its observation exactly like any
    # other. This happens inside the same transaction as the observation inserts
    # and the 'completed' flip below, so a crash can never leave a new knowledge
    # type behind with no observation to justify it -- or observations behind
    # for an extraction that isn't marked complete.
    #
    # create_or_get_dynamic_type flushes but never commits, so it composes with
    # that single final commit. A concurrent extraction proposing the same
    # category is resolved inside it via IntegrityError-catch-and-refetch.
    for proposal in validated_new_types:
        config, _created = knowledge_type_service.create_or_get_dynamic_type(
            db, proposal.policy
        )
        validated_observations.append(
            ValidatedObservation(
                knowledge_type_id=config.id,
                value=proposal.value,
                confidence=proposal.confidence,
                evidence=proposal.evidence,
            )
        )

    for obs in validated_observations:
        observation = Observation(
            submission_id=submission.id,
            guide_id=submission.guide_id,
            knowledge_type_id=obs.knowledge_type_id,
            latitude=coordinates[0] if coordinates else None,
            longitude=coordinates[1] if coordinates else None,
            geog=make_point(*coordinates) if coordinates else None,
            location_source=location_source,
            location_evidence=location_evidence,
            value=obs.value,
            confidence=obs.confidence,
            evidence=obs.evidence,
            # When the FACT was true, not when the backend received it -- for
            # a live capture these are the same instant (occurred_at defaults
            # to submitted_at, see submissions.create_or_get_submission), but
            # for an old photo or a recalled memory they can be weeks apart.
            # Getting this right matters beyond display: knowledge staleness
            # (Step 10's missing/stale/aging gap states) is computed from
            # observed_at, and crediting an old photo as "freshly observed"
            # would hide a real gap rather than reveal one.
            observed_at=submission.occurred_at or submission.submitted_at,
        )
        db.add(observation)
        # Admin moderation layer: every Observation gets a 'pending_review'
        # moderation row created atomically alongside it, in this SAME
        # transaction -- exactly the same "created atomically with its
        # parent event" pattern as ensure_pending_transcription on audio
        # attach. flush() (not commit()) assigns observation.id without
        # ending the transaction the final 'completed' flip below still needs
        # to join.
        db.flush()
        observation_moderation_service.ensure_pending_moderation(db, observation.id)

    extraction.status = "completed"
    extraction.model = settings.anthropic_model
    extraction.completed_at = datetime.now(timezone.utc)
    extraction.error_message = None
    db.commit()
    db.refresh(extraction)
    return extraction, "completed"


def maybe_trigger_extraction(db: Session, submission_id: UUID) -> None:
    """Best-effort AUTOMATIC extraction trigger. Extraction used to be purely
    explicit (POST .../extract only, called by a human/UI action) -- this is
    now called right at the moment a submission's source text FIRST becomes
    available, so a guide/admin no longer has to separately ask for it to be
    "understood":
      - services/submissions.py: right after creating a 'note', or an
        'explore' submission that already carries text.
      - services/question_answers.py: right after creating the Submission
        that represents a guide's answer.
      - services/transcriptions.py: right after a 'voice' or voice-bearing
        'explore' submission's transcription completes.

    Deliberately swallows every failure rather than propagating: the action
    that triggered this (submission creation, answer submission, transcription
    completion) must ALWAYS succeed regardless of whether automatic extraction
    itself could run right now (no source text yet, no ANTHROPIC_API_KEY
    configured, a transient provider error, ...). A human can still always
    manually trigger/retry via POST .../extract -- see start_extraction's own
    idempotency, which this reuses unchanged.
    """
    submission = db.get(Submission, submission_id)
    if submission is None:
        return

    try:
        source_text_service.resolve_source_text(db, submission)
    except source_text_service.SourceTextError:
        # Nothing to extract yet (e.g. an 'explore' submission with neither
        # text nor a completed transcription) -- not an error, just not ready.
        return

    try:
        start_extraction(db, submission_id)
    except Exception:
        logger.warning(
            "Automatic extraction trigger failed for submission %s", submission_id, exc_info=True
        )
