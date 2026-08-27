from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas.transcription import TranscriptionRead
from app.services import submissions as submission_service
from app.services import transcriptions as transcription_service

router = APIRouter(prefix="/api/v1/submissions/{submission_id}", tags=["transcriptions"])


@router.post("/transcribe", response_model=TranscriptionRead)
def trigger_transcription(submission_id: UUID, db: Session = Depends(get_db)):
    """Starts (or retries) transcription for a voice submission's uploaded
    audio, or reports the current state without calling Sarvam again if one is
    already in flight or already completed. Always returns 200 with the current
    TranscriptionRead — 'processing'/'failed' are legitimate, honest states of a
    successfully-handled request, not HTTP-level errors; only a precondition
    that blocks starting an attempt at all (submission missing/wrong type/no
    audio yet, or the server has no Sarvam key configured) is a 4xx/5xx.
    See services/transcriptions.py:start_transcription for the full idempotency
    and concurrency strategy."""
    if not settings.sarvam_api_key:
        raise HTTPException(
            status_code=503, detail="Transcription service is not configured on the server."
        )

    try:
        transcription, _outcome = transcription_service.start_transcription(db, submission_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Submission not found")
    except transcription_service.SubmissionNotAudioCapableError:
        raise HTTPException(
            status_code=400,
            detail="Transcription only applies to submissions that can carry audio "
            "(capture_type 'voice' or 'explore')",
        )
    except transcription_service.AudioNotUploadedError:
        raise HTTPException(
            status_code=400, detail="Audio has not been uploaded for this submission yet"
        )

    return transcription


@router.get("/transcription", response_model=TranscriptionRead)
def get_transcription(submission_id: UUID, db: Session = Depends(get_db)):
    """Reads the current transcription state/result — never triggers a Sarvam
    call. 404 if the submission doesn't exist, or if it does but transcription
    was never started (no audio uploaded yet)."""
    submission = submission_service.get_submission(db, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    transcription = transcription_service.get_transcription_by_submission_id(db, submission_id)
    if transcription is None:
        raise HTTPException(
            status_code=404, detail="No transcription exists yet for this submission"
        )
    return transcription
