from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.submission import Submission
from app.db.models.transcription import Transcription
from app.schemas.submission import AUDIO_CAPABLE_SUBMISSION_TYPES
from app.services.storage import get_audio_storage
from app.services.transcription.sarvam import TranscriptionProviderError, transcribe_audio


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


def start_transcription(db: Session, submission_id: UUID) -> tuple[Transcription, str]:
    """Runs one transcription attempt for a voice submission's audio, or reports
    the current state without calling the provider again if there is nothing new
    to do.

    Returns (transcription, outcome), outcome one of:
      'completed'  - a transcript is now available (this attempt or a previous one)
      'failed'     - this attempt failed; transcription.error_message is set
      'processing' - another request is already processing this submission;
                     the provider was NOT called again by this call

    Concurrency: the Transcription row is locked (SELECT ... FOR UPDATE) only
    for the brief "claim" step below -- never held across the Sarvam network
    call, which can take many seconds and must not block unrelated reads (e.g.
    GET .../transcription) or another submission's transcription entirely.
    Two genuinely concurrent calls for the SAME submission: whichever's SELECT
    FOR UPDATE commits its 'processing' claim first wins and proceeds to call
    Sarvam; the other's SELECT FOR UPDATE blocks until that commit, then sees
    'processing' already set and returns immediately without a second provider
    call. Verified with real concurrent requests -- see backend/README.md.
    """
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise LookupError(f"Submission {submission_id} not found")
    if submission.submission_type not in AUDIO_CAPABLE_SUBMISSION_TYPES:
        raise SubmissionNotAudioCapableError()
    if submission.audio_storage_key is None:
        raise AudioNotUploadedError()

    stmt = select(Transcription).where(Transcription.submission_id == submission_id).with_for_update()
    transcription = db.execute(stmt).scalar_one_or_none()
    if transcription is None:
        # Defensive fallback only -- in normal operation ensure_pending_transcription
        # already created this row atomically with the audio attach, so this
        # branch should be unreachable by the time any client can call this.
        transcription = Transcription(submission_id=submission_id, status="pending", provider="sarvam")
        db.add(transcription)

    if transcription.status == "completed":
        db.commit()
        return transcription, "completed"
    if transcription.status == "processing":
        db.commit()
        return transcription, "processing"

    # 'pending' or 'failed' -> claim this attempt. Commit here releases the row
    # lock immediately, BEFORE the slow network call below.
    transcription.status = "processing"
    transcription.attempt_count += 1
    transcription.started_at = datetime.now(timezone.utc)
    transcription.error_message = None
    db.commit()
    db.refresh(transcription)

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
