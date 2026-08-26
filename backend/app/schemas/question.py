import uuid as uuid_module
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.knowledge_state import KnowledgeState
from app.schemas.question_answer import QuestionAnswerRead


class QuestionCreate(BaseModel):
    """Request to generate a question for a specific knowledge gap (Step 12).
    Identifies the gap the same way Step 10/11's own point-based endpoints do
    -- a coordinate + evaluation_time -- plus which of the CURRENT ranked gaps
    at that point to generate for."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    # The knowledge_type slug (e.g. "snow_ice") of the specific ranked gap to
    # generate a question for -- must currently be non-fresh (missing/stale/
    # aging, Step 14) at (latitude, longitude, evaluation_time), re-verified
    # server-side, never trusted from a client-supplied snapshot.
    knowledge_type: str = Field(min_length=1, max_length=100)
    # Defaults to current server time (UTC) if omitted, exactly like Step
    # 10/11's own evaluation_time handling.
    evaluation_time: datetime | None = None
    # Stable caller-generated idempotency key, same pattern as
    # client_submission_id/client_guide_id/client_audio_id/client_location_id.
    # Nullable: omitting it means no idempotency is requested (always
    # generates fresh), matching client_location_id's optional behavior.
    client_request_id: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("client_request_id")
    @classmethod
    def validate_client_request_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            uuid_module.UUID(value)
        except ValueError as exc:
            raise ValueError("client_request_id must be a valid UUID string") from exc
        return value

    @field_validator("evaluation_time")
    @classmethod
    def require_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.tzinfo.utcoffset(value) is None):
            raise ValueError("evaluation_time must be timezone-aware")
        return value


class QuestionAssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    guide_id: UUID
    guide_name: str
    status: str
    assigned_at: datetime
    answered_at: datetime | None


class QuestionRead(BaseModel):
    """A generated question (Step 12), including the Step 10/11 provenance
    snapshotted at generation time and its current assignment, if any. Never
    includes provider credentials."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    knowledge_type_id: UUID
    knowledge_type: str
    display_name: str
    # 'missing', 'stale', or 'aging' (Step 14) -- a point-in-time SNAPSHOT of
    # the gap's state when this question was generated, never recomputed
    # (see app/db/models/question.py). Uses the same KnowledgeState Literal as
    # every other state field in this codebase -- one source of truth for the
    # set of valid state strings.
    gap_state: KnowledgeState
    target_latitude: float
    target_longitude: float
    nearest_known_place_name: str | None
    nearest_known_place_distance_meters: float | None
    safety_critical: bool
    default_priority: int
    staleness_severity_hours: float
    gap_rank: int
    question_text: str | None
    short_context: str | None
    status: str
    error_message: str | None
    attempt_count: int
    created_at: datetime
    updated_at: datetime
    # The most recent assignment, if any -- Step 12 only ever creates at most
    # one per question, but the shape allows more than one to exist later
    # (reassignment; see app/db/models/question_assignment.py).
    assignment: QuestionAssignmentRead | None = None
    # The guide's answer, if one has been submitted and persisted (Step 13).
    # Populated from the most recent QuestionAnswer row for this question --
    # this step only ever creates at most one, but reads defensively the same
    # way `assignment` above does.
    answer: QuestionAnswerRead | None = None
