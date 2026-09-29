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
from app.schemas.place_summary import PlaceResearchSummaryRead


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
    # THE authoritative coordinate for this observation -- copied from its
    # resolving Submission at extraction time (extractions.py's
    # _resolve_observation_coordinates) and NEVER re-derived from, or
    # replaced by, a nearby known Location. This is what a map (this app's
    # own, or the future Travelers website) should plot -- not
    # nearest_place_id/_name below, which are optional enrichment only and
    # frequently null even for a fully, correctly located observation. Null
    # only when the observation genuinely has no coordinate at all.
    latitude: float | None = None
    longitude: float | None = None
    # The contribution's own human-readable location, when its Submission has
    # one (the guide picked a place, searched one, or an explicit capture's
    # naming lookup succeeded). Prefer this over nearest_place_name when
    # both are present -- it describes THIS coordinate, not a nearby one.
    location_label: str | None = None
    external_place_id: str | None = None
    has_photo: bool
    has_audio: bool
    # Every photo attached to this observation's submission (multi-image
    # support) -- empty, never null, when none exists. Each URL addresses one
    # specific photo (see GET /api/v1/public/media/{submission_id}/photos/{photo_id}).
    photo_urls: list[str] = []
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
    # Set only for a CATEGORY-knowledge observation (the primary system --
    # Observation.category_knowledge_id), naming the assigned category it
    # verifies. For those rows knowledge_type/display_name above carry the
    # category's slug/display_name and safety_critical is False, so every
    # existing consumer keeps rendering them without special-casing. Null
    # for a hazard/knowledge-type observation.
    category_slug: str | None = None
    category_display_name: str | None = None


class PublicObservationList(BaseModel):
    items: list[PublicObservation]
    total: int


class PublicCategoryLabel(BaseModel):
    """A category's identity only -- for place cards/lists. The full
    per-category state lives on PublicLocationDetail.categories."""

    slug: str
    kind: str
    display_name: str


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
    # Only set when this summary was returned as a NEIGHBOUR of another
    # Location (PublicLocationDetail.nearby) -- metres from that place.
    distance_meters: float | None = None
    # Active categories (same relevance floor as the detail page): the
    # primary place_type first, then themes most relevant first.
    categories: list[PublicCategoryLabel] = []


class PublicVerifiedKnowledge(BaseModel):
    """One VERIFIED CategoryKnowledge item -- a fact a guide's approved
    observation confirmed (last_verified_at is only ever set by moderation
    approval, see app/services/category_knowledge.py::mark_verified).
    Unverified/pending items are never public. `fresh` is derived, never
    stored: now <= last_verified_at + freshness_duration_hours."""

    knowledge_id: UUID
    knowledge_text: str
    last_verified_at: datetime
    fresh: bool


class PublicLocationCategory(BaseModel):
    """One of a Location's ACTIVE categories -- the same set
    get_location_coverage returns (relevance >= category_coverage_min_relevance,
    active catalog row), most relevant first. `state` is that function's
    derived coverage state: 'fresh' | 'stale' | 'partially_stale' | 'missing'
    ('missing' = no guide has verified anything for this category yet)."""

    slug: str
    # 'theme' (what the place is about) or 'place_type' (what it is).
    kind: str
    display_name: str
    relevance: int
    is_primary: bool
    state: str
    verified_knowledge: list[PublicVerifiedKnowledge] = []


class PublicPlaceQuestionAnswer(BaseModel):
    """One APPROVED answer to a PlaceQuestion. 'Approved' means
    SubmissionReview.status == 'approved' -- the reward-eligibility gate on
    the answering Submission itself (see app/services/submission_review.py),
    NOT ObservationModeration, which is 1:1 with an Observation and has
    nothing to review for the common case of an answer producing zero
    Observations (or, for a category-driven PlaceQuestion, producing a
    CategoryKnowledge-linked Observation reviewed separately -- either way,
    reward-eligibility is the correct public-visibility gate here, not
    knowledge moderation)."""

    submission_id: UUID
    answer_text: str
    guide_name: str
    answered_at: datetime


class PublicPlaceQuestion(BaseModel):
    """One active PlaceQuestion with >= 1 approved answer. A question with
    zero approved answers is never returned -- see
    list_public_place_questions."""

    place_question_id: UUID
    question_text: str
    context_note: str | None
    answers: list[PublicPlaceQuestionAnswer]


class PublicRouteStop(BaseModel):
    """One stop on a Route, joined to its Location and a location-level
    freshness bucket. `status` reuses the KnowledgeState vocabulary so the
    frontend's existing freshness helpers apply unchanged -- see
    settings.route_stop_freshness_window_hours/route_stop_aging_threshold_hours."""

    route_stop_id: UUID
    location_id: UUID
    name: str
    sequence_order: int
    stop_label: str | None
    elevation_meters: int | None
    latitude: float
    longitude: float
    # 'missing' when this stop's Location has no APPROVED observation at all.
    status: KnowledgeState
    last_observed_at: datetime | None
    age_hours: float | None


class PublicRoute(BaseModel):
    route_id: UUID
    slug: str
    name: str
    description: str | None
    stops: list[PublicRouteStop]


class PublicLocationDetail(PublicLocationSummary):
    conditions: list[PublicConditionState]
    recent_observations: list[PublicObservation]
    photo_count: int
    voice_story_count: int
    # WEB-RESEARCHED, UNVERIFIED orientation content -- deliberately its own
    # field, never merged into `description` above or into `conditions`
    # (live data) or `recent_observations` (TrailMind-verified traveler
    # contributions). None when this Location has never had a summary
    # attempt. See app/db/models/location_research_summary.py.
    research_summary: PlaceResearchSummaryRead | None = None
    # Active PlaceQuestions with at least one approved answer. Empty when
    # this Location has none (yet).
    popular_questions: list[PublicPlaceQuestion] = []
    # None for the overwhelming majority of Locations -- only set when this
    # Location is a stop on a seeded Route. See get_public_route_for_location.
    route: PublicRoute | None = None
    # This Location's active categories with TrailMind-VERIFIED knowledge
    # only -- a separate trust layer from research_summary (web research)
    # and recent_observations (individual live reports).
    categories: list[PublicLocationCategory] = []
    # Other Locations within public_nearby_radius_meters, nearest first.
    nearby: list[PublicLocationSummary] = []


class PublicSearchResult(BaseModel):
    query: str
    locations: list[PublicLocationSummary]
    observations: list[PublicObservation]
