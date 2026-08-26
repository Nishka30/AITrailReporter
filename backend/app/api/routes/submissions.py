import uuid as uuid_module
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas.submission import SubmissionCreate, SubmissionRead
from app.services import guides as guide_service
from app.services import submissions as submission_service
from app.services.audio_validation import InvalidAudioUploadError, validate_audio_upload
from app.services.storage import get_audio_storage

router = APIRouter(prefix="/api/v1/submissions", tags=["submissions"])


@router.post("", response_model=SubmissionRead, status_code=201)
def create_submission(payload: SubmissionCreate, response: Response, db: Session = Depends(get_db)):
    """Ingests a submission: a text note (capture_type 'note') or the metadata for
    a voice observation (capture_type 'voice', audio uploaded separately via
    POST /{submission_id}/audio). Idempotent on client_submission_id: a repeat
    request with the same id and matching payload returns the existing submission
    with 200 instead of creating a duplicate. A repeat request with the same id but
    different payload is rejected with 409 rather than silently overwriting the
    original."""
    guide = guide_service.get_guide(db, payload.guide_id)
    if guide is None:
        raise HTTPException(status_code=404, detail="Guide not found")

    try:
        submission, created = submission_service.create_or_get_submission(db, payload)
    except submission_service.SubmissionConflictError:
        raise HTTPException(
            status_code=409,
            detail="client_submission_id was already used with different submission data",
        )

    response.status_code = 201 if created else 200
    return submission


@router.post("/{submission_id}/audio", response_model=SubmissionRead)
async def upload_submission_audio(
    submission_id: UUID,
    response: Response,
    file: UploadFile = File(...),
    client_audio_id: str = Form(...),
    duration_seconds: float | None = Form(default=None),
    db: Session = Depends(get_db),
):
    """Uploads and durably attaches audio to a 'voice' submission created via
    POST /api/v1/submissions. Idempotent on client_audio_id (a second, distinct
    stable id from client_submission_id — see Submission.client_audio_id): a
    retried request with the same client_audio_id returns the existing reference
    (200) instead of storing a duplicate file; the same submission with a
    DIFFERENT client_audio_id is rejected with 409. See
    services/submissions.py:attach_audio_to_submission for the full idempotency
    and race-safety strategy."""
    try:
        uuid_module.UUID(client_audio_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="client_audio_id must be a valid UUID string")

    submission = submission_service.get_submission(db, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    if submission.submission_type != "voice":
        raise HTTPException(
            status_code=400,
            detail="Audio can only be attached to a submission with capture_type 'voice'",
        )

    # Read at most one byte past the configured cap: enough to detect an oversized
    # upload without needing to buffer an unbounded amount of client-controlled data.
    max_size = settings.max_audio_upload_size_bytes
    audio_bytes = await file.read(max_size + 1)

    try:
        validate_audio_upload(
            content_type=file.content_type,
            filename=file.filename,
            size_bytes=len(audio_bytes),
            max_size_bytes=max_size,
        )
    except InvalidAudioUploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    try:
        submission, created = submission_service.attach_audio_to_submission(
            db,
            submission_id,
            client_audio_id,
            audio_bytes,
            content_type=file.content_type,
            original_filename=file.filename or "recording",
            duration_seconds=duration_seconds,
            storage=get_audio_storage(),
        )
    except submission_service.AudioConflictError:
        raise HTTPException(
            status_code=409,
            detail="client_audio_id was already used with a different audio attachment "
            "for this submission",
        )

    response.status_code = 201 if created else 200
    return submission
