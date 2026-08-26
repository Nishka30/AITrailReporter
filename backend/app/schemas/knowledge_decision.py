from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.knowledge_state import KnowledgeState, KnowledgeStateResult


class GuideCandidate(BaseModel):
    """One active guide whose latest known location is geographically relevant
    to a ranked gap's target location (Step 11). `rank` 1 is the best candidate
    -- see app/services/knowledge_decisions.py for the ranking rule."""

    rank: int
    guide_id: UUID
    guide_name: str
    latest_location_recorded_at: datetime
    # evaluation_time - latest_location_recorded_at, in hours. Can be negative
    # if the guide's latest ping was recorded AFTER evaluation_time -- an honest
    # fact, not filtered out (see Part G of this step's spec: no arbitrary
    # recency cutoff without an existing configured policy for one).
    location_age_hours: float
    distance_meters: float
    ranking_reasons: list[str]


class RankedGap(BaseModel):
    """One non-fresh knowledge type from Step 10's gap list, ranked and
    enriched with candidate guides who could plausibly be asked about it."""

    rank: int
    knowledge_type_id: UUID
    knowledge_type: str
    display_name: str
    # 'missing', 'stale', or 'aging' here (Step 14) -- never 'fresh' (a fresh
    # knowledge type is not a gap and never appears in this list).
    state: KnowledgeState
    safety_critical: bool
    default_priority: int
    # 0.0 for 'missing' (the concept doesn't apply); for 'aging', hours past
    # freshness_expires_at; for 'stale', hours past aging_expires_at (or past
    # freshness_expires_at if no aging period is configured) -- this is
    # KnowledgeTypeState.severity_hours (Step 10), carried through unchanged.
    # Field kept under its ORIGINAL name for backward compatibility with
    # already-persisted Question.staleness_severity_hours provenance -- see
    # app/services/knowledge_decisions.py for the exact formula.
    staleness_severity_hours: float
    ranking_reasons: list[str]
    # The coordinate this gap was evaluated at. Modeled per-gap (not just once
    # at the top level) because a future step may evaluate gaps at DIFFERENT
    # target locations (e.g. along a guide's route) -- in this step's only
    # call pattern (one point-based evaluation) every gap's target is
    # identical to the request's own latitude/longitude, but the field is
    # already shaped for that later case.
    target_latitude: float
    target_longitude: float
    guide_candidates: list[GuideCandidate]
    # Candidate rank 1, or null if guide_candidates is empty. NEVER a
    # fabricated guide -- a gap with zero relevant guides is a valid, honest
    # result (see Part H of this step's spec).
    selected_guide: GuideCandidate | None


class KnowledgeDecisionResult(BaseModel):
    """Full deterministic decision output for one geographic point/time (Step
    11): Step 10's knowledge state (unchanged, reused as-is) plus ranked gaps,
    each with its own candidate guides. No LLM involved anywhere in this
    result -- see app/services/knowledge_decisions.py."""

    knowledge_state: KnowledgeStateResult
    ranked_gaps: list[RankedGap]
