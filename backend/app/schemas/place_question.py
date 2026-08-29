"""Popular-question response/request shapes (Step 18).

Deliberately a much smaller shape than QuestionRead: a popular question has no
gap provenance, no ranking, no assignment and no per-guide state, so none of
those fields exist here. Presenting it with the same shape as a knowledge-gap
question would imply a ranking relationship that does not exist.
"""

import uuid as uuid_module
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PlaceQuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    location_id: UUID
    question_text: str
    # One of PLACE_QUESTION_CONTRIBUTION_KINDS. The app uses this to foreground
    # the right control (camera, recorder, text) -- it never decides the kind
    # itself, and never derives the reward from it either (see reward_points).
    contribution_kind: str
    # Short grounded line saying what research established about this place.
    # Null when research found nothing specific enough to state honestly.
    context_note: str | None = None
    display_order: int
    # The real web sources this question was derived from. Present so the
    # provenance of a researched question is inspectable rather than taken on
    # trust; null when the research run recorded none.
    source_urls: list[str] | None = None
    created_at: datetime
    # What contributing to THIS question is currently worth, resolved per
    # contribution_kind from reward_rules server-side. The app displays this
    # number and never computes its own -- which is why a photo request can be
    # worth more than a status check without the app knowing anything about
    # rates.
    reward_points: int = 0


class PlaceQuestionResearchRead(BaseModel):
    """The research lifecycle for one place. Exposed so a caller (and the
    admin UI) can tell 'we researched and genuinely found nothing' apart from
    'research has not run yet' or 'research failed' -- three very different
    situations that an empty question list alone cannot distinguish."""

    model_config = ConfigDict(from_attributes=True)

    status: str
    researched_at: datetime | None
    error_message: str | None
    attempt_count: int


class PlaceQuestionList(BaseModel):
    location_id: UUID
    location_name: str
    questions: list[PlaceQuestionRead]
    research: PlaceQuestionResearchRead | None


class GuidePlaceQuestions(BaseModel):
    """What the mobile Questions tab reads for its 'Popular questions about
    this place' section. `location_*` is null when the guide has no recorded
    location, or when no known place is within range -- in which case
    `questions` is empty and the app says so plainly rather than showing
    questions about somewhere the guide isn't."""

    location_id: UUID | None
    location_name: str | None
    distance_meters: float | None
    questions: list[PlaceQuestionRead]


class PlaceQuestionAnswerCreate(BaseModel):
    guide_id: UUID
    # Same idempotency contract as QuestionAnswerCreate.client_answer_id, and
    # the same value is reused as the reward's idempotency key -- see
    # app/services/place_question_answers.py.
    client_answer_id: str = Field(min_length=1, max_length=255)
    answer_text: str = Field(min_length=1)
    answered_at: datetime | None = None

    @field_validator("client_answer_id")
    @classmethod
    def validate_client_answer_id(cls, value: str) -> str:
        try:
            uuid_module.UUID(value)
        except ValueError as exc:
            raise ValueError("client_answer_id must be a valid UUID string") from exc
        return value

    @field_validator("answered_at")
    @classmethod
    def require_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.tzinfo.utcoffset(value) is None):
            raise ValueError("answered_at must be timezone-aware")
        return value


class PlaceQuestionAnswerRead(BaseModel):
    place_question_id: UUID
    submission_id: UUID
    guide_id: UUID
    answer_text: str
    answered_at: datetime
    # Points granted by THIS request: 0 on an idempotent replay, because the
    # guide was already credited the first time. The app should treat its own
    # provisional total as superseded by GET /guides/{id}/rewards, not add
    # this number a second time.
    points_awarded: int
