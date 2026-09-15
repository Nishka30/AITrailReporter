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
from app.schemas.submission_review import SubmissionReviewRead
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
    # Admin-approval gate on rewards (Step 19) -- counts from submission_reviews,
    # a completely separate table/lifecycle from the observation counts above
    # (see app/db/models/submission_review.py for why).
    contribution_pending_review_count: int
    contribution_approved_count: int
    contribution_rejected_count: int


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


class ContributionQueueItem(BaseModel):
    """One row in the Contribution Review queue -- one Submission/answer being
    reviewed for PAYMENT, not for knowledge accuracy (that is the separate
    Review Queue/ObservationModeration above). See
    app/db/models/submission_review.py for why these are two different
    reviews of two different things."""

    submission_id: UUID
    submission_type: str
    guide_id: UUID
    guide_name: str
    raw_text: str | None
    submitted_at: datetime
    latitude: float | None
    longitude: float | None
    # The place this contribution concerns, when resolvable -- directly for a
    # place-question answer (via its location_id), otherwise left null rather
    # than guessed from raw lat/lon (a nearby-place guess belongs in a human's
    # judgement while reviewing, not in this list row).
    location_id: UUID | None
    location_name: str | None
    # The exact text of the question this answers, if it answers one at all
    # (a free-form 'explore'/'memory' contribution has none of these).
    question_text: str | None
    has_audio: bool
    has_photo: bool
    review: SubmissionReviewRead
    # What this is worth if approved -- resolved live from reward_rules by
    # the SAME rule_key frozen on the review row, so an admin sees the
    # CURRENT rate even if it has changed since the guide contributed (the
    # rate actually paid is whatever is active at the moment of approval,
    # per reward_service.award's existing, unchanged behavior).
    current_rule_points: int


class ContributionQueueResult(BaseModel):
    items: list[ContributionQueueItem]
    total: int
    page: int
    page_size: int


class ContributionDetail(BaseModel):
    """Full detail for one contribution under review -- everything an admin
    needs to decide, without a second request: the content, the place, the
    question (if any), and the contributor."""

    item: ContributionQueueItem
    audio: SubmissionAudioRead | None
    photo: SubmissionPhotoRead | None
    transcript: TranscriptionRead | None
    guide_phone_number: str | None


class PlaceSummary(BaseModel):
    location_id: UUID
    name: str
    latitude: float
    longitude: float
    category: str | None
    subcategory: str | None
    source: str
    nearby_observation_count: int
    pending_review_count: int
    approved_count: int
    # The multi-category classification (see
    # app/services/places/category_catalog.py), most relevant first -- same
    # data PlaceDetail already exposes, added here too so the Places list
    # cards can show real category chips instead of only the legacy
    # category/subcategory pair.
    categories: list["PlaceCategoryDetail"] = []


class PlaceQueueResult(BaseModel):
    items: list[PlaceSummary]
    total: int
    page: int
    page_size: int


class PlaceCategoryOption(BaseModel):
    """One filterable place_type, with how many DISTINCT Locations currently
    carry it -- an entry in a PlaceCategoryGroup's `options` list."""

    kind: str
    slug: str
    display_name: str
    group: str
    count: int
    priority: int


class PlaceCategoryGroup(BaseModel):
    """One user-friendly filter section (e.g. 'Food & Drink'), grouping
    several place_types by their shared theme -- see
    app/services/places/category_ui_groups.py for how the grouping is
    derived from the existing category catalog."""

    key: str
    label: str
    count: int
    options: list[PlaceCategoryOption]


class PlaceDetail(BaseModel):
    location_id: UUID
    name: str
    description: str | None
    latitude: float
    longitude: float
    category: str | None
    subcategory: str | None
    source: str
    provider: str | None
    external_place_id: str | None
    formatted_address: str | None
    # The multi-category classification (see
    # app/services/places/category_catalog.py). Additive alongside the single
    # category/subcategory pair above, which is unchanged -- these are the
    # several things this place is at once, each with how much it defines it.
    categories: list["PlaceCategoryDetail"] = []
    created_at: datetime
    recent_observations: list[ReviewQueueItem]


class PlaceCategoryDetail(BaseModel):
    kind: str
    slug: str
    display_name: str
    relevance: int
    confidence: float
    is_primary: bool
    source: str


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


class ContributorQueueResult(BaseModel):
    items: list[ContributorSummary]
    total: int
    page: int
    page_size: int


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


class AdminQuestionQueueResult(BaseModel):
    items: list[AdminQuestionSummary]
    total: int
    page: int
    page_size: int
