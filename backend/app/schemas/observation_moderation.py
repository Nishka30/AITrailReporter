from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

# The single source of truth for every moderation status string in this
# codebase, mirroring how app/schemas/knowledge_state.py's KnowledgeState is
# the one place 'fresh'/'aging'/'stale'/'missing' are spelled out. Every other
# module compares/branches on THIS type rather than re-declaring the string
# literals (see app/services/observation_moderation.py).
ModerationStatus = Literal["pending_review", "approved", "rejected"]

# A small, closed set of rejection reasons -- keeps the review queue
# analyzable and matches this codebase's existing convention of enumerations
# over free text wherever a value will later be filtered or counted.
RejectionReason = Literal["inaccurate", "unsafe", "duplicate", "poor_quality", "not_useful", "other"]


class ObservationModerationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    observation_id: UUID
    status: ModerationStatus
    decided_by: str | None
    decided_at: datetime | None
    rejection_reason: RejectionReason | None
    rejection_note: str | None
    created_at: datetime
    updated_at: datetime


class RejectObservationRequest(BaseModel):
    reason: RejectionReason
    note: str | None = None


class ChangeModerationDecisionRequest(BaseModel):
    """Explicitly switches an ALREADY-DECIDED observation to the opposite
    decision. Deliberately a separate action from approve/reject (see
    app/services/observation_moderation.py:change_decision) -- an admin must
    take a distinct, deliberate step to reverse a prior decision rather than
    the same single-click endpoint silently overwriting it."""

    status: Literal["approved", "rejected"]
    reason: RejectionReason | None = None
    note: str | None = None
