from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.observation import ObservationRead


class ExtractionRead(BaseModel):
    """Extraction lifecycle/result for one Submission. Distinct from
    TranscriptionRead and SubmissionRead on purpose -- see
    app/db/models/extraction.py. Never includes provider credentials.
    `observations` is populated by app/services/extractions.py, not by
    from_attributes alone (it isn't a column on the Extraction row)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    submission_id: UUID
    status: str
    provider: str
    model: str | None
    error_message: str | None
    attempt_count: int
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    observations: list[ObservationRead] = []
