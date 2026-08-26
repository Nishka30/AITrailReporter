from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TranscriptionRead(BaseModel):
    """Transcription lifecycle/result for one voice Submission. Distinct from
    SubmissionRead on purpose — see app/db/models/transcription.py. Never
    includes a filesystem path or provider credentials."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    submission_id: UUID
    status: str
    transcript: str | None
    language_code: str | None
    language_probability: float | None
    provider: str
    model: str | None
    mode: str | None
    provider_request_id: str | None
    error_message: str | None
    attempt_count: int
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
