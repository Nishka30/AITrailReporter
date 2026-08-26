"""Resolves the single normalized text a Submission should be extracted from
(Step 9), so app/services/extractions.py doesn't need to know whether it's
looking at a note or a voice submission. Reads only -- never calls Saaras;
voice transcription remains the separate, explicit flow from Step 8."""

from app.db.models.submission import Submission
from app.services import transcriptions as transcription_service
from sqlalchemy.orm import Session


class SourceTextError(Exception):
    """Base for every reason resolve_source_text() can't return usable text."""


class EmptySourceTextError(SourceTextError):
    """A 'note' submission's text_content is missing/blank."""


class TranscriptionMissingError(SourceTextError):
    """A 'voice' submission has no Transcription row yet -- transcription was
    never triggered (POST .../transcribe was never called)."""


class TranscriptionNotReadyError(SourceTextError):
    """A 'voice' submission's Transcription exists but hasn't finished yet."""

    def __init__(self, status: str):
        self.status = status
        super().__init__(f"Transcription is still {status}")


class TranscriptionFailedError(SourceTextError):
    """A 'voice' submission's last transcription attempt failed."""


class EmptyTranscriptError(SourceTextError):
    """A 'voice' submission's Transcription is 'completed' but the transcript is
    blank -- defensive: Step 8's transcribe_audio already rejects empty
    transcripts before ever marking a Transcription 'completed', so this should
    be unreachable in practice, but extraction must never proceed on it."""


def resolve_source_text(db: Session, submission: Submission) -> str:
    """Returns the text to feed to LLM extraction for this submission, or raises
    a SourceTextError subclass describing exactly why none is available yet."""
    # 'answer' (Step 13: a guide's answer to an assigned Question, represented
    # as a Submission -- see services/question_answers.py) has its content
    # directly in raw_text, exactly like 'note' -- reuses the identical branch
    # rather than a parallel extraction path, per this step's explicit
    # "do not duplicate extraction logic" requirement.
    if submission.submission_type in ("note", "answer"):
        text = (submission.raw_text or "").strip()
        if not text:
            raise EmptySourceTextError()
        return text

    if submission.submission_type == "voice":
        transcription = transcription_service.get_transcription_by_submission_id(
            db, submission.id
        )
        if transcription is None:
            raise TranscriptionMissingError()
        if transcription.status in ("pending", "processing"):
            raise TranscriptionNotReadyError(transcription.status)
        if transcription.status == "failed":
            raise TranscriptionFailedError()

        text = (transcription.transcript or "").strip()
        if not text:
            raise EmptyTranscriptError()
        return text

    raise SourceTextError(f"Unsupported submission_type: {submission.submission_type!r}")
