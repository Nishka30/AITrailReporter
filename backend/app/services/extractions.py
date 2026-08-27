from datetime import datetime, timezone
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
from app.services import observations as observation_service
from app.services import source_text as source_text_service
from app.services.extraction.anthropic_provider import ExtractionProviderError, extract_observations
from app.services.extraction.validation import (
    InvalidExtractionOutputError,
    ValidatedObservation,
    validate_llm_output,
)


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


def _resolve_observation_coordinates(db: Session, submission: Submission) -> tuple[float, float] | None:
    """The coordinate to attach to this submission's observations, or None if
    nothing is known -- never fabricated. Prefers the submission's own
    latitude/longitude if the client supplied them; otherwise falls back to the
    guide's latest known GuideLocation AT OR BEFORE submitted_at (the location
    the guide was actually at when they made this report, not wherever they are
    by the time extraction happens to run)."""
    if submission.latitude is not None and submission.longitude is not None:
        return float(submission.latitude), float(submission.longitude)

    guide_location = guide_location_service.get_latest_location_at_or_before(
        db, submission.guide_id, submission.submitted_at
    )
    if guide_location is not None:
        return float(guide_location.latitude), float(guide_location.longitude)

    return None


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

    coordinates = _resolve_observation_coordinates(db, submission)
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
        db.add(
            Observation(
                submission_id=submission.id,
                guide_id=submission.guide_id,
                knowledge_type_id=obs.knowledge_type_id,
                latitude=coordinates[0] if coordinates else None,
                longitude=coordinates[1] if coordinates else None,
                geog=make_point(*coordinates) if coordinates else None,
                value=obs.value,
                confidence=obs.confidence,
                evidence=obs.evidence,
                observed_at=submission.submitted_at,
            )
        )

    extraction.status = "completed"
    extraction.model = settings.anthropic_model
    extraction.completed_at = datetime.now(timezone.utc)
    extraction.error_message = None
    db.commit()
    db.refresh(extraction)
    return extraction, "completed"
