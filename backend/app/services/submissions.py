from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.submission import Submission
from app.schemas.submission import SubmissionCreate
from app.services import extractions as extraction_service
from app.services import transcriptions as transcription_service
from app.services.storage.base import AudioStorage, MediaStorage


class SubmissionConflictError(Exception):
    """Raised when a client_submission_id is reused with a payload that doesn't
    match the original submission it was first used for."""

    def __init__(self, existing: Submission):
        self.existing = existing
        super().__init__(
            f"client_submission_id {existing.client_submission_id!r} was already used "
            "with different submission data"
        )


class AudioConflictError(Exception):
    """Raised when a submission that already has audio attached receives another
    audio upload with a different client_audio_id — i.e. an attempt to attach a
    second, distinct recording rather than retry the same one."""

    def __init__(self, existing: Submission):
        self.existing = existing
        super().__init__(
            f"submission {existing.id} already has audio attached under a "
            "different client_audio_id"
        )


class PhotoConflictError(Exception):
    """Photo equivalent of AudioConflictError (Step 16): the submission already
    has a photo attached under a DIFFERENT client_photo_id. Replacing an
    already-attached photo is deliberately not supported, matching audio."""

    def __init__(self, existing: Submission):
        self.existing = existing
        super().__init__(
            f"submission {existing.id} already has a photo attached under a "
            "different client_photo_id"
        )


def get_submission_by_client_id(db: Session, client_submission_id: str) -> Submission | None:
    stmt = select(Submission).where(Submission.client_submission_id == client_submission_id)
    return db.execute(stmt).scalar_one_or_none()


def get_submission(db: Session, submission_id: UUID) -> Submission | None:
    return db.get(Submission, submission_id)


def _ensure_compatible(existing: Submission, data: SubmissionCreate) -> None:
    if (
        existing.guide_id != data.guide_id
        or existing.submission_type != data.capture_type
        or existing.raw_text != data.text_content
    ):
        raise SubmissionConflictError(existing)


def create_or_get_submission(db: Session, data: SubmissionCreate) -> tuple[Submission, bool]:
    """Create a submission, or return the existing one if client_submission_id was
    already used for an equivalent submission. Raises SubmissionConflictError if the
    same client_submission_id is reused with different data instead of silently
    overwriting the original.

    Race-safe the same way as guides.create_or_get_guide: the DB unique constraint
    on client_submission_id is the real guarantee, an IntegrityError on a concurrent
    duplicate insert is caught and resolved by re-fetching the winner's row.
    """
    existing = get_submission_by_client_id(db, data.client_submission_id)
    if existing is not None:
        _ensure_compatible(existing, data)
        return existing, False

    submission = Submission(
        guide_id=data.guide_id,
        client_submission_id=data.client_submission_id,
        submission_type=data.capture_type,
        raw_text=data.text_content,
        submitted_at=data.submitted_at or datetime.now(timezone.utc),
        status="received",
    )
    db.add(submission)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = get_submission_by_client_id(db, data.client_submission_id)
        if existing is not None:
            _ensure_compatible(existing, data)
            return existing, False
        raise
    db.refresh(submission)
    # Automatic extraction (see extractions.py:maybe_trigger_extraction):
    # a 'note' always has text immediately; an 'explore' submission MAY --
    # resolve_source_text handles both, and a voice-only 'explore' (no text
    # yet) simply isn't ready, so this is a safe no-op for it. Never raises.
    extraction_service.maybe_trigger_extraction(db, submission.id)
    return submission, True


def attach_audio_to_submission(
    db: Session,
    submission_id: UUID,
    client_audio_id: str,
    audio_bytes: bytes,
    content_type: str,
    original_filename: str,
    duration_seconds: float | None,
    storage: AudioStorage,
) -> tuple[Submission, bool]:
    """Attaches durably-stored audio to a 'voice' submission. Idempotent on
    client_audio_id, mirroring the client_submission_id/client_location_id pattern
    used elsewhere:

    - No audio attached yet -> saves the file, records the reference, returns
      (submission, True).
    - Audio already attached under this SAME client_audio_id -> this is a retry of
      a request whose response was lost; returns the existing reference without
      writing another file, (submission, False).
    - Audio already attached under a DIFFERENT client_audio_id -> raises
      AudioConflictError (a real conflict — this step does not support replacing
      an already-attached recording).

    Race safety: the submission row is locked with SELECT ... FOR UPDATE for the
    duration of this function, so two concurrent attach attempts for the SAME
    submission are fully serialized — the second one to acquire the lock sees
    whatever the first one committed and takes the idempotent-replay or conflict
    path above, never a duplicate attachment. The one known gap (documented in
    README): if the process crashes between writing the file to disk and
    committing the row update, the file on disk is orphaned (never referenced by
    any submission) — acceptable for this step, not a correctness issue for the
    data that IS recorded.
    """
    stmt = select(Submission).where(Submission.id == submission_id).with_for_update()
    submission = db.execute(stmt).scalar_one_or_none()
    if submission is None:
        raise LookupError(f"Submission {submission_id} not found")

    if submission.client_audio_id is not None:
        if submission.client_audio_id == client_audio_id:
            db.commit()  # releases the row lock acquired above
            return submission, False
        db.commit()
        raise AudioConflictError(submission)

    stored = storage.save(audio_bytes, original_filename)
    submission.client_audio_id = client_audio_id
    submission.audio_storage_key = stored.storage_key
    submission.audio_content_type = content_type
    submission.audio_original_filename = original_filename
    submission.audio_size_bytes = stored.size_bytes
    submission.audio_duration_seconds = duration_seconds
    # Step 8: create the Transcription tracking row in the SAME transaction as
    # the audio attach, so "audio attached" and "transcription pending" commit
    # atomically together — no window where audio exists but nothing tracks its
    # transcription state.
    transcription_service.ensure_pending_transcription(db, submission_id)
    db.commit()
    db.refresh(submission)
    return submission, True


def attach_photo_to_submission(
    db: Session,
    submission_id: UUID,
    client_photo_id: str,
    photo_bytes: bytes,
    content_type: str,
    original_filename: str,
    storage: MediaStorage,
) -> tuple[Submission, bool]:
    """Attaches a durably-stored photo to an 'explore' submission (Step 16).

    Structurally identical to attach_audio_to_submission above — same
    idempotency contract on client_photo_id, same SELECT ... FOR UPDATE row
    lock serializing concurrent attach attempts for the same submission, same
    documented orphaned-file-on-crash gap. Two deliberate differences:

    - No transcription row is created. A photo has no transcript, and inventing
      a pipeline stage that does nothing would be dishonest state.
    - No duration is recorded, for the same reason (see
      SubmissionPhotoMetadata).

    A photo does NOT by itself make a submission extractable: extraction reads
    source TEXT (app/services/source_text.py), and this step does not do image
    understanding. An Explore photo contribution therefore always carries the
    guide's own text alongside it — that text is what becomes observations,
    while the photo is durable evidence attached to the same submission. This
    is stated plainly rather than implying the image is being analysed.
    """
    stmt = select(Submission).where(Submission.id == submission_id).with_for_update()
    submission = db.execute(stmt).scalar_one_or_none()
    if submission is None:
        raise LookupError(f"Submission {submission_id} not found")

    if submission.client_photo_id is not None:
        if submission.client_photo_id == client_photo_id:
            db.commit()  # releases the row lock acquired above
            return submission, False
        db.commit()
        raise PhotoConflictError(submission)

    stored = storage.save(photo_bytes, original_filename)
    submission.client_photo_id = client_photo_id
    submission.photo_storage_key = stored.storage_key
    submission.photo_content_type = content_type
    submission.photo_original_filename = original_filename
    submission.photo_size_bytes = stored.size_bytes
    db.commit()
    db.refresh(submission)
    return submission, True
