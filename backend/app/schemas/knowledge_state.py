from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.geographic_context import NearestKnownPlace

# The single source of truth for every knowledge state string in this
# codebase (Step 14 adds 'aging') -- every other module that needs to
# compare/branch on a state imports THIS, rather than hardcoding the string
# literals a second time (see app/services/knowledge_decisions.py,
# app/services/question_generation/prompt.py, app/schemas/question.py).
KnowledgeState = Literal["fresh", "aging", "stale", "missing"]


class KnowledgeTypeState(BaseModel):
    """The evaluated state of ONE active knowledge type at a specific point and
    time (Step 10, extended in Step 14 with 'aging'). `freshness_window_hours`,
    `aging_threshold_hours`, and `geographic_relevance_radius_meters` are
    copied from that type's own KnowledgeTypeConfig row at evaluation time --
    no state is ever judged against one global threshold. All
    observation-specific fields are null for 'missing' -- never a misleading
    fabricated value.

    Aging semantics (Step 14) -- given
    freshness_expires_at = observed_at + freshness_window_hours and (when
    aging_threshold_hours is configured) aging_expires_at =
    freshness_expires_at + aging_threshold_hours:

    - evaluation_time <= freshness_expires_at                        -> fresh
    - freshness_expires_at < evaluation_time <= aging_expires_at      -> aging
    - evaluation_time > aging_expires_at                              -> stale
      (or, when aging_threshold_hours is NULL/0 -- no aging period configured
      -- evaluation_time > freshness_expires_at goes DIRECTLY to stale;
      see app/services/knowledge_state.py for the exact boundary-inclusive
      comparisons)."""

    knowledge_type_id: UUID
    knowledge_type: str
    display_name: str
    state: KnowledgeState

    latest_observation_id: UUID | None
    observed_at: datetime | None
    age_hours: float | None
    distance_meters: float | None

    freshness_window_hours: int
    freshness_expires_at: datetime | None
    # Copied from KnowledgeTypeConfig.aging_threshold_hours -- NULL means this
    # knowledge type has no configured aging/grace period at all (the
    # pre-Step-14 behavior: fresh transitions directly to stale).
    aging_threshold_hours: int | None
    # freshness_expires_at + aging_threshold_hours. Null whenever
    # aging_threshold_hours itself is null (no aging period is configured for
    # this knowledge type) OR there is no observation at all ('missing') --
    # never a fabricated timestamp. Present (a real, if zero-width, boundary)
    # even when aging_threshold_hours == 0 -- see knowledge_state.py's
    # _evaluate_one_type for why a zero-width window still produces a
    # well-defined instant rather than being treated as "no period".
    aging_expires_at: datetime | None
    geographic_relevance_radius_meters: int

    # Carried through from KnowledgeTypeConfig so a later ranking step (Step 11)
    # doesn't need to re-join/re-query this metadata for every gap.
    safety_critical: bool
    default_priority: int

    # Generalized "how far past its expiry" measure (Step 14), always >= 0:
    #   missing / fresh -> 0.0
    #   aging           -> evaluation_time - freshness_expires_at
    #   stale           -> evaluation_time - aging_expires_at (or, when no
    #                      aging period is configured, evaluation_time -
    #                      freshness_expires_at)
    # This is the SAME quantity Step 11 previously computed for itself as
    # "staleness_severity_hours" (using only freshness_expires_at, since
    # aging didn't exist yet) -- Step 10 is now the single place this is
    # computed; Step 11's RankedGap.staleness_severity_hours (kept under its
    # existing field name for backward compatibility with already-persisted
    # Question provenance) is now simply this value, carried through.
    severity_hours: float


class KnowledgeStateSummary(BaseModel):
    total_active_types: int
    fresh_count: int
    aging_count: int
    stale_count: int
    missing_count: int
    # aging_count + stale_count + missing_count (Step 14, Part D) --
    # "knowledge that isn't currently fully trustworthy and nearby": no
    # longer fully fresh (aging), fresh but has now fully expired (stale), or
    # was never observed at all (missing). 'fresh' is the only non-gap state.
    gap_count: int


class KnowledgeStateResult(BaseModel):
    latitude: float
    longitude: float
    evaluation_time: datetime
    knowledge_types: list[KnowledgeTypeState]
    summary: KnowledgeStateSummary
    # The non-fresh subset of knowledge_types (state != 'fresh'), pre-filtered so
    # a later ranking step (Step 11) can consume this directly.
    gaps: list[KnowledgeTypeState]


class GuideKnowledgeStateResult(BaseModel):
    guide_id: UUID
    location_recorded_at: datetime
    nearest_known_place: NearestKnownPlace | None
    knowledge_state: KnowledgeStateResult
