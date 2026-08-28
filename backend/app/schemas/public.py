"""Response shapes for the public traveller website API (/api/v1/public/*).

Every shape here is a deliberately reduced view of an existing internal
entity: guide_id/phone numbers/storage keys/moderation-internal fields
(decided_by, rejection_reason, pending/rejected rows) are never included.
See app/services/public_content.py for how these are assembled -- always
filtered to ObservationModeration.status == 'approved', reusing the same
join pattern as app/services/admin_review.py (that module's own docstring
calls this out as the intended reuse)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.knowledge_state import KnowledgeState


class PublicKnowledgeType(BaseModel):
    """One active KnowledgeTypeConfig, stripped to what a traveller-facing UI
    needs to render an unknown/new category gracefully -- no threshold
    internals (freshness_window_hours etc. stay backend-only)."""

    knowledge_type: str
    display_name: str
    safety_critical: bool


class PublicConditionState(BaseModel):
    """One knowledge type's current state at a place, for the 'Right Now'
    module. The state itself (fresh/aging/stale/missing) and its timing are
    always computed from an APPROVED observation only -- see
    evaluate_public_knowledge_state in app/services/public_content.py, which
    reuses knowledge_state.py's own boundary math but swaps in an
    approved-only observation lookup so a pending/rejected report can never
    influence what a traveller sees. Wording ('Updated recently' etc.) is a
    presentation concern and stays entirely on the frontend."""

    knowledge_type: str
    display_name: str
    safety_critical: bool
    state: KnowledgeState
    observed_at: datetime | None
    age_hours: float | None
    severity_hours: float
    # Present only when state != 'missing' -- always an APPROVED observation,
    # safe to pass to GET /api/v1/public/observations/{id}.
    latest_observation_id: UUID | None


class PublicLocationConditions(BaseModel):
    latitude: float
    longitude: float
    evaluation_time: datetime
    conditions: list[PublicConditionState]


class PublicObservation(BaseModel):
    """One approved Observation, presented for a public audience. Mirrors
    ReviewQueueItem's shape (app/schemas/admin.py) minus guide_id/moderation
    internals, plus public-safe media links."""

    observation_id: UUID
    knowledge_type: str
    display_name: str
    safety_critical: bool
    value: dict
    evidence: str | None
    observed_at: datetime
    submission_type: str
    guide_name: str
    has_photo: bool
    has_audio: bool
    photo_url: str | None
    audio_url: str | None
    # Only ever populated from a COMPLETED transcription of a submission that
    # produced at least one approved observation -- see
    # get_public_observation/list_public_observations.
    transcript: str | None = None
    # The nearest known Location within geographic_context_radius_meters of
    # this observation's own coordinate, reusing
    # app/services/geographic_context.py unchanged -- lets the frontend turn
    # a single photo/story into an entry point back to its place ("See what
    # else travellers noticed here"). Null when the observation has no
    # coordinate, or no known place is within range.
    nearest_place_id: UUID | None = None
    nearest_place_name: str | None = None


class PublicObservationList(BaseModel):
    items: list[PublicObservation]
    total: int


class PublicLocationSummary(BaseModel):
    location_id: UUID
    name: str
    description: str | None
    latitude: float
    longitude: float
    approved_observation_count: int
    # Max observed_at among this place's approved, nearby observations --
    # None when it has none yet. Used for "recently updated" discovery
    # sorting; never fabricated when absent.
    last_activity_at: datetime | None


class PublicLocationDetail(PublicLocationSummary):
    conditions: list[PublicConditionState]
    recent_observations: list[PublicObservation]
    photo_count: int
    voice_story_count: int


class PublicSearchResult(BaseModel):
    query: str
    locations: list[PublicLocationSummary]
    observations: list[PublicObservation]
