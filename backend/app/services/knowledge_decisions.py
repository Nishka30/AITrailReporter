"""Deterministic gap-ranking + relevant-guide-selection engine (Step 11) -- no
LLM calls. Answers: "at this moment, what information should the system try
to collect next, and which guide is the best available guide to ask?"

This module NEVER recomputes freshness/staleness/missing itself -- it consumes
app/services/knowledge_state.py's result (Step 10) as the sole source of truth
for gap detection, and only adds ranking + guide selection on top.
"""

from datetime import datetime

from app.schemas.knowledge_decision import GuideCandidate, KnowledgeDecisionResult, RankedGap
from app.schemas.knowledge_state import KnowledgeTypeState
from app.services import guide_locations as guide_location_service
from app.services import knowledge_state as knowledge_state_service
from sqlalchemy.orm import Session

# --- default_priority direction --------------------------------------------
# KnowledgeTypeConfig.default_priority has no documented direction anywhere in
# this codebase (inspected: model, seed migration, README -- no comment on
# which end is "more important"). This is an explicit APPLICATION-LEVEL
# interpretation, not a database-established policy: HIGHER default_priority
# means MORE important. Reasoning: the column defaults to 0, the natural
# "baseline/nothing configured" floor, and "priority: 5" reads as more urgent
# than "priority: 0" in ordinary usage. Centralized here, in exactly one
# place, so if this interpretation ever needs to flip, only this constant's
# sign needs to change -- nowhere else in the codebase encodes this rule.
_HIGHER_DEFAULT_PRIORITY_IS_MORE_IMPORTANT = True


def _default_priority_sort_component(default_priority: int) -> int:
    return -default_priority if _HIGHER_DEFAULT_PRIORITY_IS_MORE_IMPORTANT else default_priority


# --- gap state urgency ordering ---------------------------------------------
# Step 14, Part D's explicit requirement: missing > stale > aging (after
# safety-criticality). A single, centralized mapping -- exactly one place in
# the codebase encodes this ordering, rather than repeating an if/elif chain
# per state wherever ranking is needed.
_GAP_STATE_URGENCY_RANK: dict[str, int] = {"missing": 0, "stale": 1, "aging": 2}


def _staleness_severity_hours(gap: KnowledgeTypeState) -> float:
    """The gap's severity, in hours -- Step 14 moved the actual computation
    into Step 10 (KnowledgeTypeState.severity_hours), which now accounts for
    the aging period (see app/services/knowledge_state.py's _evaluate_one_type
    for the exact formula: aging measures past freshness_expires_at, stale
    measures past aging_expires_at when an aging period is configured, or
    past freshness_expires_at otherwise). This function just carries that
    single authoritative value through -- kept as its own function, and this
    field kept under its EXISTING name (`staleness_severity_hours` on
    RankedGap, matching the already-persisted Question.staleness_severity_hours
    provenance column), for backward compatibility -- Step 11 originally
    computed this by re-deriving it from freshness_expires_at alone, before
    'aging' existed; nothing about the field's MEANING ("how far past this
    gap's relevant expiry boundary are we") has changed, only its formula for
    states that didn't exist yet when it was first written. Always 0.0 for
    'missing' (Step 10 already returns 0.0 there -- no observation exists to
    measure severity from)."""
    return gap.severity_hours


def _gap_ranking_reasons(gap: KnowledgeTypeState, staleness_severity_hours: float) -> list[str]:
    reasons: list[str] = []
    if gap.safety_critical:
        reasons.append("Safety-critical knowledge type")
    if gap.state == "missing":
        reasons.append("No geographically relevant observation exists")
    elif gap.state == "aging":
        reasons.append(
            f"Observation is aging -- {staleness_severity_hours:.1f} hours past its "
            "freshness window, still within its grace period"
        )
    else:
        boundary = "aging grace period" if gap.aging_expires_at is not None else "freshness window"
        reasons.append(f"Observation is stale -- {staleness_severity_hours:.1f} hours past its {boundary}")
    reasons.append(f"Default priority: {gap.default_priority}")
    return reasons


def _gap_sort_key(gap: KnowledgeTypeState, staleness_severity_hours: float) -> tuple:
    """Deterministic ranking tuple, compared lexicographically (component 1
    dominates component 2, which dominates component 3, ...) -- an ordered
    ranking tuple rather than one blended numeric score, so each criterion's
    precedence is unambiguous and independently explainable (see
    ranking_reasons) rather than hidden inside an arbitrary weighted formula.

    1. Safety-critical first (per this step's explicit policy).
    2. Gap state urgency: 'missing' ranks ahead of 'stale', which ranks ahead
       of 'aging' (Step 14, Part D) -- an APPLICATION-LEVEL rule (not a
       database-configured policy), via the centralized
       _GAP_STATE_URGENCY_RANK mapping above. 'missing' means there is no
       evidence at all; 'stale' means evidence exists but has fully expired;
       'aging' means evidence exists and is still within its configured grace
       period -- the least urgent of the three gap states.
    3. Higher default_priority first (see the module-level constant above for
       the documented direction interpretation).
    4. More severe first within the SAME state (larger time-past-expiry).
       Always 0.0 for 'missing', which is harmless here since criterion 2
       already fully separates missing from the other two states before this
       component is ever compared.
    5. Final deterministic tie-breaker: knowledge_type name, ascending.
    """
    return (
        0 if gap.safety_critical else 1,
        _GAP_STATE_URGENCY_RANK[gap.state],
        _default_priority_sort_component(gap.default_priority),
        -staleness_severity_hours,
        gap.knowledge_type,
    )


def _rank_guide_candidates(
    db: Session,
    target_latitude: float,
    target_longitude: float,
    radius_meters: float,
    evaluation_time: datetime,
) -> list[GuideCandidate]:
    """Active guides whose LATEST known location (by recorded_at, never
    insertion order) is within radius_meters of the gap's target -- reuses
    app/services/guide_locations.py::find_nearby_guides UNCHANGED (already
    implements exactly this: DISTINCT ON latest-per-guide, PostGIS
    ST_DWithin/ST_Distance, active guides only). Ranking on top is plain
    Python over that small, already-filtered result set -- no new SQL, no
    Haversine math.

    Ranking tuple: (distance_meters ascending, location_age_hours ascending
    [more recent first], guide_id ascending as the final deterministic
    tie-breaker). Distance is primary per this step's spec ("closer is
    better"); recency only distinguishes candidates at equal distance.
    """
    rows = guide_location_service.find_nearby_guides(
        db, target_latitude, target_longitude, radius_meters
    )

    enriched = [
        (row, (evaluation_time - row["recorded_at"]).total_seconds() / 3600.0) for row in rows
    ]
    enriched.sort(key=lambda pair: (pair[0]["distance_meters"], pair[1], str(pair[0]["guide_id"])))

    candidates: list[GuideCandidate] = []
    for rank, (row, location_age_hours) in enumerate(enriched, start=1):
        distance_meters = float(row["distance_meters"])
        reasons = [
            f"{distance_meters:.0f}m from the gap location "
            f"(within the {radius_meters:.0f}m relevance radius for this knowledge type)",
            f"Latest known location recorded {location_age_hours:.1f} hours "
            "before evaluation time"
            if location_age_hours >= 0
            else f"Latest known location recorded {-location_age_hours:.1f} hours "
            "after evaluation time",
        ]
        candidates.append(
            GuideCandidate(
                rank=rank,
                guide_id=row["guide_id"],
                guide_name=row["name"],
                latest_location_recorded_at=row["recorded_at"],
                location_age_hours=location_age_hours,
                distance_meters=distance_meters,
                ranking_reasons=reasons,
            )
        )
    return candidates


def evaluate_knowledge_decision(
    db: Session, latitude: float, longitude: float, evaluation_time: datetime
) -> KnowledgeDecisionResult:
    """Full decision flow for one point/time: evaluate knowledge state (Step
    10, unmodified) -> extract its gaps -> rank them deterministically -> for
    each ranked gap, find and rank relevant guide candidates. `evaluation_time`
    is required and must be timezone-aware (validate/default it at the API
    boundary with knowledge_state.resolve_evaluation_time, exactly as Step 10
    does) -- this service never calls now() itself, for the same replayability
    reason Step 10 doesn't.
    """
    knowledge_state = knowledge_state_service.evaluate_knowledge_state(
        db, latitude, longitude, evaluation_time
    )

    scored_gaps = []
    for gap in knowledge_state.gaps:
        staleness_severity_hours = _staleness_severity_hours(gap)
        sort_key = _gap_sort_key(gap, staleness_severity_hours)
        scored_gaps.append((sort_key, gap, staleness_severity_hours))
    scored_gaps.sort(key=lambda item: item[0])

    ranked_gaps: list[RankedGap] = []
    for rank, (_, gap, staleness_severity_hours) in enumerate(scored_gaps, start=1):
        candidates = _rank_guide_candidates(
            db, latitude, longitude, gap.geographic_relevance_radius_meters, evaluation_time
        )
        ranked_gaps.append(
            RankedGap(
                rank=rank,
                knowledge_type_id=gap.knowledge_type_id,
                knowledge_type=gap.knowledge_type,
                display_name=gap.display_name,
                state=gap.state,
                safety_critical=gap.safety_critical,
                default_priority=gap.default_priority,
                staleness_severity_hours=staleness_severity_hours,
                ranking_reasons=_gap_ranking_reasons(gap, staleness_severity_hours),
                target_latitude=latitude,
                target_longitude=longitude,
                guide_candidates=candidates,
                selected_guide=candidates[0] if candidates else None,
            )
        )

    return KnowledgeDecisionResult(knowledge_state=knowledge_state, ranked_gaps=ranked_gaps)
