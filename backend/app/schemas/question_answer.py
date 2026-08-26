import uuid as uuid_module
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class QuestionAnswerCreate(BaseModel):
    """A guide's answer to a specific assigned Question (Step 13, Part D)."""

    guide_id: UUID
    # Stable caller-generated idempotency key, same convention as
    # client_submission_id/client_guide_id/client_location_id/client_audio_id/
    # client_request_id. Required (not nullable/optional) -- see
    # app/db/models/question_answer.py for why an answer must always have one.
    client_answer_id: str = Field(min_length=1, max_length=255)
    answer_text: str = Field(min_length=1)
    # When the guide actually answered (device-local time). Defaults to
    # current server time (UTC) if omitted, matching evaluation_time/
    # submitted_at handling elsewhere in this project.
    answered_at: datetime | None = None

    @field_validator("client_answer_id")
    @classmethod
    def validate_client_answer_id(cls, value: str) -> str:
        try:
            uuid_module.UUID(value)
        except ValueError as exc:
            raise ValueError("client_answer_id must be a valid UUID string") from exc
        return value

    @field_validator("answer_text")
    @classmethod
    def validate_answer_text_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("answer_text must not be blank")
        return value

    @field_validator("answered_at")
    @classmethod
    def require_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.tzinfo.utcoffset(value) is None):
            raise ValueError("answered_at must be timezone-aware")
        return value


class QuestionAnswerRead(BaseModel):
    """A persisted answer. Never includes provider credentials -- there are
    none here; answers involve no LLM call (see Part E of this step)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    question_id: UUID
    assignment_id: UUID
    guide_id: UUID
    answer_text: str
    submission_id: UUID
    answered_at: datetime
    created_at: datetime
    updated_at: datetime
