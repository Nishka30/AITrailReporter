import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.submission import Submission
from app.db.models.transcription import Transcription
from app.schemas.submission import AUDIO_CAPABLE_SUBMISSION_TYPES
from app.services.storage import get_audio_storage
from app.services.transcription.sarvam import TranscriptionProviderError, transcribe_audio

logger = logging.getLogger(__name__)


class SubmissionNotAudioCapableError(Exception):
    """Raised when transcription is requested for a submission type that cannot
    carry audio at all (see AUDIO_CAPABLE_SUBMISSION_TYPES) — e.g. a 'note'.

    Renamed from SubmissionNotVoiceError in Step 17: 'explore' submissions can
    now carry a voice note too, so "not voice" stopped being the actual reason
    a transcription request is refused. The check is driven by the SAME
    allow-list the upload route uses, so a submission can never be in the state
    "audio accepted but transcription refused"."""


# Backwards-compatible alias: kept so any caller written against the Step 8 name
# keeps working rather than breaking on an import that silently moved.
SubmissionNotVoiceError = SubmissionNotAudioCapableError


class AudioNotUploadedError(Exception):
    """Raised when transcription is requested before audio has been uploaded."""


def get_transcription_by_submission_id(db: Session, submission_id: UUID) -> Transcription | None:
    stmt = select(Transcription).where(Transcription.submission_id == submission_id)
    return db.execute(stmt).scalar_one_or_none()


def ensure_pending_transcription(db: Session, submission_id: UUID) -> Transcription:
    """Called once, in the SAME transaction as attach_audio_to_submission's first
    successful attach (see services/submissions.py) — so "audio attached" and
    "transcription tracking exists" commit atomically together; there is no
    window where a voice submission has audio but no Transcription row.
    Idempotent: a pre-existing row (e.g. this being called again) is returned
    unchanged, never reset back to 'pending'.

    Uses db.flush(), not db.commit() -- the caller (attach_audio_to_submission)
    owns the transaction boundary and commits once, for both changes together.
    """
    existing = get_transcription_by_submission_id(db, submission_id)
    if existing is not None:
        return existing
    transcription = Transcription(submission_id=submission_id, status="pending", provider="sarvam")
    db.add(transcription)
    db.flush()
    return transcription


def _mark_failed(db: Session, transcription: Transcription, message: str) -> Transcription:
    transcription.status = "failed"
    transcription.error_message = message
    db.commit()
    db.refresh(transcription)
    return transcription


def _is_stale_processing(transcription: Transcription) -> bool:
    """True when a 'processing' claim is old enough that the attempt which made
    it cannot still be running.

    This is the only way out of a 'processing' row whose worker died mid-flight
    — a deploy, a restart, an OOM kill. Without it such a row is permanently
    unretryable: every later attempt sees 'processing' and returns without
    doing anything, and the guide's recording is stranded with no transcript
    and no error to explain why. The window is deliberately far longer than the
    batch job budget so a slow-but-alive attempt is never stolen and billed
    twice.
    """
    if transcription.started_at is None:
        # 'processing' with no start time should be impossible (they are set in
        # the same commit). If it happens, the row is already inconsistent and
        # blocking retries forever is the worse failure.
        return True
    cutoff = datetime.now(timezone.utc) - timedelta(
        seconds=settings.transcription_stale_processing_seconds
    )
    return transcription.started_at < cutoff


def claim_transcription(db: Session, submission_id: UUID) -> tuple[Transcription, str]:
    """Decides whether a new attempt should run, and atomically claims it if so.

    Returns (transcription, outcome), outcome one of:
      'claimed'    - this caller now owns an attempt; it MUST go on to call
                     run_claimed_transcription (directly, or via a background
                     task) or the row is left 'processing' until it goes stale
      'completed'  - a transcript already exists; nothing to do
      'processing' - a live attempt is already running; nothing to do

    This is the fast, database-only half of transcription, split out from the
    slow provider half so an HTTP request can claim an attempt (milliseconds)
    and hand the actual Sarvam work to a background task. That split is what
    keeps the upload response independent of how long transcription takes.

    Concurrency: the Transcription row is locked (SELECT ... FOR UPDATE) for the
    brief claim only — never across the provider call, which can take many
    seconds and must not block unrelated reads (e.g. GET .../transcription) or
    another submission's transcription entirely. Two genuinely concurrent calls
    for the SAME submission: whichever's SELECT FOR UPDATE commits its
    'processing' claim first wins; the other blocks until that commit, then sees
    'processing' already set and returns without a second provider call.

    Retry semantics (both 'pending' and 'failed' are claimable) are what make a
    failed transcription retryable by simply calling this again — there is no
    separate retry path and no second Transcription row per submission.
    """
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise LookupError(f"Submission {submission_id} not found")
    if submission.submission_type not in AUDIO_CAPABLE_SUBMISSION_TYPES:
        raise SubmissionNotAudioCapableError()
    if submission.audio_storage_key is None:
        raise AudioNotUploadedError()

    stmt = (
        select(Transcription).where(Transcription.submission_id == submission_id).with_for_update()
    )
    transcription = db.execute(stmt).scalar_one_or_none()
    if transcription is None:
        # Defensive fallback only -- in normal operation ensure_pending_transcription
        # already created this row atomically with the audio attach, so this
        # branch should be unreachable by the time any client can call this.
        transcription = Transcription(
            submission_id=submission_id, status="pending", provider="sarvam"
        )
        db.add(transcription)

    if transcription.status == "completed":
        db.commit()
        return transcription, "completed"
    if transcription.status == "processing" and not _is_stale_processing(transcription):
        db.commit()
        return transcription, "processing"
    if transcription.status == "processing":
        logger.warning(
            "Reclaiming stale 'processing' transcription for submission %s "
            "(started_at=%s, attempt_count=%s) — the attempt that claimed it "
            "did not finish",
            submission_id,
            transcription.started_at,
            transcription.attempt_count,
        )

    # 'pending', 'failed', or a stale 'processing' -> claim this attempt. The
    # commit here releases the row lock immediately, BEFORE any slow work.
    transcription.status = "processing"
    transcription.attempt_count += 1
    transcription.started_at = datetime.now(timezone.utc)
    transcription.error_message = None
    db.commit()
    db.refresh(transcription)
    return transcription, "claimed"


def run_claimed_transcription(db: Session, submission_id: UUID) -> tuple[Transcription, str]:
    """Performs the slow half of an attempt already claimed by
    claim_transcription: read the stored audio, call Sarvam, persist the result.

    Returns (transcription, 'completed' | 'failed'). Must only be called for a
    submission this process (or the request that scheduled this one) has just
    claimed — it does not re-check or re-take the claim.
    """
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise LookupError(f"Submission {submission_id} not found")
    transcription = get_transcription_by_submission_id(db, submission_id)
    if transcription is None:
        raise LookupError(f"Transcription for submission {submission_id} not found")

    storage = get_audio_storage()
    try:
        audio_bytes = storage.read_bytes(submission.audio_storage_key)
    except FileNotFoundError:
        return _mark_failed(db, transcription, "Stored audio file is missing on the server."), "failed"

    try:
        result = transcribe_audio(
            audio_bytes,
            filename=submission.audio_original_filename or "recording",
            content_type=submission.audio_content_type,
            # Lets the provider pick the right Sarvam endpoint up front: the
            # synchronous one rejects anything over 30s outright, so a long
            # recording goes straight to the batch job API instead of burning
            # an attempt on a guaranteed 400.
            duration_seconds=(
                float(submission.audio_duration_seconds)
                if submission.audio_duration_seconds is not None
                else None
            ),
        )
    except TranscriptionProviderError as exc:
        return _mark_failed(db, transcription, exc.message), "failed"

    transcription.status = "completed"
    transcription.transcript = result.transcript
    transcription.language_code = result.language_code
    transcription.language_probability = result.language_probability
    transcription.model = result.model
    transcription.mode = result.mode
    transcription.provider_request_id = result.request_id
    transcription.error_message = None
    transcription.completed_at = datetime.now(timezone.utc)
    # Committed BEFORE extraction is triggered, deliberately: the transcript is
    # the guide's actual words and is valuable on its own, so a later Anthropic
    # failure must never be able to lose it or leave this row un-completed.
    db.commit()
    db.refresh(transcription)

    # Automatic extraction (see extractions.py:maybe_trigger_extraction) --
    # a voice/explore submission's source text only becomes available once
    # transcription completes, so this is where it triggers for those types
    # (mirrors the trigger at creation time for 'note'/'answer'/explore-with-
    # text in services/submissions.py and question_answers.py). Imported here
    # rather than at module level: extractions.py -> source_text.py ->
    # transcriptions.py already forms one direction of this dependency, so a
    # top-level import here would be a circular import.
    from app.services import extractions as extraction_service

    extraction_service.maybe_trigger_extraction(db, submission_id)

    return transcription, "completed"


def start_transcription(db: Session, submission_id: UUID) -> tuple[Transcription, str]:
    """Claims and runs one transcription attempt in the caller's own thread and
    session, or reports the current state without calling the provider again if
    there is nothing new to do.

    Returns (transcription, outcome), outcome one of 'completed', 'failed', or
    'processing' — unchanged from before the claim/run split, so existing
    callers and tests keep their exact contract. Production request handling now
    prefers claim_transcription() + a background task instead, so that a slow
    provider never holds an HTTP response open.
    """
    transcription, outcome = claim_transcription(db, submission_id)
    if outcome != "claimed":
        return transcription, outcome
    return run_claimed_transcription(db, submission_id)


def process_transcription_in_background(submission_id: UUID) -> None:
    """Runs an ALREADY-CLAIMED transcription attempt outside the request that
    scheduled it, on its own database session.

    Scheduled via FastAPI's BackgroundTasks (see routes/submissions.py and
    routes/transcriptions.py), which runs it after the response has been sent.
    Its own Session is essential: the request's session is closed by the
    get_db() dependency as soon as the response is returned, so reusing it here
    would fail on the first query.

    NEVER raises. A background task that raises is logged by Starlette and
    otherwise invisible, so every failure is caught and recorded on the row
    instead — and if the process dies before that can happen, the row's stale
    'processing' claim is reclaimable by the next attempt (see
    _is_stale_processing).
    """
    # Imported here rather than at module level to keep this module importable
    # without a configured database, which the existing tests rely on.
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        run_claimed_transcription(db, submission_id)
    except Exception:
        logger.exception("Background transcription failed for submission %s", submission_id)
        try:
            transcription = get_transcription_by_submission_id(db, submission_id)
            if transcription is not None and transcription.status == "processing":
                _mark_failed(db, transcription, "Transcription failed unexpectedly on the server.")
        except Exception:
            logger.exception(
                "Could not record the background transcription failure for submission %s",
                submission_id,
            )
    finally:
        db.close()


def schedule_transcription(background_tasks, db: Session, submission_id: UUID) -> str:
    """Claims an attempt now and queues the provider work to run after the
    response is sent. Returns the claim outcome ('claimed'/'completed'/
    'processing').

    This is the single entry point every HTTP route uses. The claim happens
    synchronously so the response already reflects the true new state
    ('processing' rather than a stale 'pending'), while the part that can take
    seconds — reading the audio back out of Supabase, Sarvam, then Anthropic
    extraction — happens afterwards, off the request.

    NEVER raises: audio that is durably stored must never be rejected because
    transcription could not be started, exactly the contract
    maybe_trigger_transcription had before it.
    """
    try:
        _transcription, outcome = claim_transcription(db, submission_id)
    except Exception:
        logger.warning(
            "Could not claim transcription for submission %s", submission_id, exc_info=True
        )
        return "failed"
    if outcome == "claimed":
        background_tasks.add_task(process_transcription_in_background, submission_id)
    return outcome


def maybe_trigger_transcription(db: Session, submission_id: UUID) -> None:
    """Best-effort SYNCHRONOUS transcription trigger. NEVER raises.

    Retained for callers with no request/BackgroundTasks context (scripts,
    tests, and any future scheduled sweep). The HTTP paths use
    schedule_transcription() instead so the provider call never runs inside a
    request — see services/submissions.py's attach_audio_to_submission, which
    no longer triggers transcription itself for exactly that reason.
    """
    try:
        start_transcription(db, submission_id)
    except Exception:
        logger.warning(
            "Automatic transcription trigger failed for submission %s", submission_id, exc_info=True
        )
