import uuid as uuid_module
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# 'note' (text) and 'voice' (audio, Step 7) are ingestable. Widen this tuple (and
# the Literal below) when another capture type is actually implemented — do not
# accept values the backend can't yet do anything useful with.
SUPPORTED_CAPTURE_TYPES = ("note", "voice")


class SubmissionCreate(BaseModel):
    guide_id: UUID
    # Stable client-generated id (e.g. a mobile app's local UUID). Submission
    # ingestion is idempotent on this value: a repeat request with the same
    # client_submission_id returns the already-created submission instead of making
    # another, as long as the resubmitted payload matches the original.
    client_submission_id: str = Field(min_length=1, max_length=255)
    capture_type: Literal["note", "voice"]
    # Required for 'note' (the text IS the submission). Must be omitted/null for
    # 'voice' — a voice submission's content is the audio, attached afterwards via
    # POST /api/v1/submissions/{submission_id}/audio; there is no transcript field
    # yet (that's a later step, not this one).
    text_content: str | None = Field(default=None, min_length=1)
    # When the device captured this, not when the server received it. Defaults to
    # server time if the client doesn't supply one.
    submitted_at: datetime | None = None

    @field_validator("client_submission_id")
    @classmethod
    def validate_client_submission_id(cls, value: str) -> str:
        try:
            uuid_module.UUID(value)
        except ValueError as exc:
            raise ValueError("client_submission_id must be a valid UUID string") from exc
        return value

    @field_validator("submitted_at")
    @classmethod
    def require_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.tzinfo.utcoffset(value) is None):
            raise ValueError("submitted_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_text_content_for_capture_type(self) -> "SubmissionCreate":
        if self.capture_type == "note" and not self.text_content:
            raise ValueError("text_content is required for capture_type 'note'")
        if self.capture_type == "voice" and self.text_content is not None:
            raise ValueError(
                "text_content must not be supplied for capture_type 'voice' — "
                "upload the audio separately via POST /api/v1/submissions/{id}/audio"
            )
        return self


class SubmissionAudioRead(BaseModel):
    """Durable audio metadata for a 'voice' submission. Deliberately omits the
    server storage key/path — that is an internal implementation detail, never
    exposed to clients (see app/services/storage/)."""

    model_config = ConfigDict(from_attributes=True)

    content_type: str
    original_filename: str
    size_bytes: int
    duration_seconds: float | None


class SubmissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    guide_id: UUID
    client_submission_id: str | None
    submission_type: str
    raw_text: str | None
    status: str
    submitted_at: datetime
    created_at: datetime
    updated_at: datetime
    # Populated from the ORM's Submission.audio property (see db/models/submission.py)
    # — present only once audio has actually been uploaded for this submission.
    audio: SubmissionAudioRead | None = None
