"""Response shapes for the admin API (/api/v1/admin/*). These are read
models assembled explicitly by app/services/admin_*.py, joining together
existing entities (Observation, Submission, Guide, Transcription,
KnowledgeTypeConfig, Location, Question) plus the new ObservationModeration
row -- exactly the same "explicit joins in the service layer, no ORM
relationships" convention used everywhere else in this codebase.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.knowledge_state import KnowledgeStateResult
from app.schemas.observation_moderation import ObservationModerationRead
from app.schemas.submission import SubmissionAudioRead, SubmissionPhotoRead
from app.schemas.transcription import TranscriptionRead


class AdminOverview(BaseModel):
    """Real, currently-true counts only -- never a fabricated or placeholder
    number. Every field here is a direct COUNT()/aggregate query at request
    time (see app/services/admin_overview.py)."""

    total_guides: int
    total_submissions: int
    total_observations: int
    pending_review_count: int
    approved_count: int
    rejected_count: int
    safety_critical_pending_count: int
    active_knowledge_type_count: int
    questions_generated_count: int
    questions_pending_assignment_count: int


class ReviewQueueItem(BaseModel):
    """One row in the Review Queue / Knowledge browser -- one Observation,
    never one Submission (a submission can yield several observations, each
    moderated independently)."""

    observation_id: UUID
    knowledge_type: str
    display_name: str
    safety_critical: bool
    value: dict
    confidence: float | None
    evidence: str | None
    latitude: float | None
    longitude: float | None
    observed_at: datetime
    created_at: datetime
    submission_id: UUID
    submission_type: str
    guide_id: UUID
    guide_name: str
    moderation: ObservationModerationRead
    nearest_known_place_name: str | None = None
    nearest_known_place_distance_meters: float | None = None
    # True when this observation's KnowledgeTypeConfig was created dynamically
    # (Step 16, Case B) within the recent past -- the frontend uses this to
    # show a "new knowledge type" affordance without any schema change; see
    # app/services/admin_review.py for the exact window.
    knowledge_type_is_new: bool = False


class ReviewQueueResult(BaseModel):
    items: list[ReviewQueueItem]
    total: int
    page: int
    page_size: int


class RelatedObservation(BaseModel):
    """Another observation of the SAME knowledge type, near this one in space
    and time -- the honest stand-in for automatic conflict/duplicate
    detection (which does not exist in this system): the admin reads these
    and judges duplication/conflict themselves; the backend never claims to
    have detected one."""

    observation_id: UUID
    value: dict
    confidence: float | None
    evidence: str | None
    observed_at: datetime
    guide_name: str
    distance_meters: float | None
    moderation_status: str


class SiblingObservation(BaseModel):
    """Another observation produced by the SAME source submission -- surfaced
    so the Review Detail UI can show "this submission also produced N other
    observations" instead of re-rendering duplicate source media per
    observation."""

    observation_id: UUID
    knowledge_type: str
    display_name: str
    moderation_status: str


class ReviewSourceSubmission(BaseModel):
    """The raw evidence this observation was extracted from -- never the
    rewritten/re-summarized text, always the original. Audio/photo expose only
    safe backend-served metadata (see SubmissionAudioRead/SubmissionPhotoRead),
    never a filesystem path or storage credential."""

    submission_id: UUID
    submission_type: str
    raw_text: str | None
    submitted_at: datetime
    audio: SubmissionAudioRead | None
    photo: SubmissionPhotoRead | None
    transcript: TranscriptionRead | None = None


class ReviewDetail(BaseModel):
    observation: ReviewQueueItem
    source: ReviewSourceSubmission
    knowledge_context: KnowledgeStateResult | None
    related_observations: list[RelatedObservation]
    sibling_observations: list[SiblingObservation]


class PlaceSummary(BaseModel):
    location_id: UUID
    name: str
    latitude: float
    longitude: float
    nearby_observation_count: int
    pending_review_count: int
    approved_count: int


class PlaceDetail(BaseModel):
    location_id: UUID
    name: str
    description: str | None
    latitude: float
    longitude: float
    recent_observations: list[ReviewQueueItem]


class ContributorSummary(BaseModel):
    guide_id: UUID
    name: str
    is_active: bool
    submission_count: int
    observation_count: int
    approved_count: int
    rejected_count: int
    pending_review_count: int
    last_active_at: datetime | None


class ContributorDetail(ContributorSummary):
    phone_number: str | None
    recent_observations: list[ReviewQueueItem]


class AdminQuestionSummary(BaseModel):
    """Read-only visibility into the existing Question/QuestionAssignment
    lifecycle for admins -- does not touch or redesign that workflow."""

    question_id: UUID
    knowledge_type: str
    display_name: str
    gap_state: str
    status: str
    safety_critical: bool
    target_latitude: float
    target_longitude: float
    nearest_known_place_name: str | None
    question_text: str | None
    assignment_status: str | None
    assigned_guide_name: str | None
    created_at: datetime
