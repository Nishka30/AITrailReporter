from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas.extraction import ExtractionRead
from app.services import extractions as extraction_service
from app.services import source_text as source_text_service
from app.services import submissions as submission_service

router = APIRouter(prefix="/api/v1/submissions/{submission_id}", tags=["extractions"])


@router.post("/extract", response_model=ExtractionRead)
def trigger_extraction(submission_id: UUID, db: Session = Depends(get_db)):
    """Starts (or retries) LLM structured extraction for a submission's resolved
    source text (a note's text, or a voice submission's completed transcript),
    or reports the current state without calling the provider again if one is
    already in flight or already completed. Always returns 200 with the current
    ExtractionRead -- 'processing'/'failed' are legitimate, honest states of a
    successfully-handled request, not HTTP-level errors; only a precondition
    that blocks starting an attempt at all (submission missing, no usable source
    text yet, or the server has no LLM key configured) is a 4xx/5xx. See
    services/extractions.py:start_extraction for the full idempotency and
    concurrency strategy."""
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=503, detail="Extraction service is not configured on the server."
        )

    try:
        extraction, _outcome = extraction_service.start_extraction(db, submission_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Submission not found")
    except source_text_service.EmptySourceTextError:
        raise HTTPException(
            status_code=400, detail="Submission has no usable text content to extract from."
        )
    except source_text_service.TranscriptionMissingError:
        raise HTTPException(
            status_code=400,
            detail="Voice submission has not been transcribed yet. "
            "Call POST .../transcribe first.",
        )
    except source_text_service.TranscriptionNotReadyError as exc:
        raise HTTPException(
            status_code=400, detail=f"Voice transcription is still {exc.status}."
        )
    except source_text_service.TranscriptionFailedError:
        raise HTTPException(
            status_code=400,
            detail="Voice transcription failed. Retry transcription before extracting.",
        )
    except source_text_service.EmptyTranscriptError:
        raise HTTPException(
            status_code=400, detail="Transcription completed but produced an empty transcript."
        )

    return extraction_service.build_extraction_read(db, extraction)


@router.get("/extraction", response_model=ExtractionRead)
def get_extraction(submission_id: UUID, db: Session = Depends(get_db)):
    """Reads the current extraction state/result -- never triggers an LLM call.
    404 if the submission doesn't exist, or if it does but extraction was never
    started."""
    submission = submission_service.get_submission(db, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    extraction = extraction_service.get_extraction_by_submission_id(db, submission_id)
    if extraction is None:
        raise HTTPException(
            status_code=404, detail="No extraction exists yet for this submission"
        )

    return extraction_service.build_extraction_read(db, extraction)
