from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ObservationRead(BaseModel):
    """A validated, persisted observation (Step 9). Assembled explicitly by
    app/services/extractions.py (which joins in the human-readable knowledge_type
    string from KnowledgeTypeConfig) rather than built directly from the
    Observation ORM row via from_attributes -- Observation only stores
    knowledge_type_id, and the codebase deliberately does no ORM-level
    relationships (joins are explicit SQL throughout, see app/services/*.py)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    submission_id: UUID
    guide_id: UUID
    knowledge_type: str
    latitude: float | None
    longitude: float | None
    value: dict
    confidence: float | None
    evidence: str | None
    observed_at: datetime
    created_at: datetime
