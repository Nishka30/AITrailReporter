"""Deterministic policy for turning a volatility CLASSIFICATION into a real
freshness_duration_hours value, for CategoryKnowledge (the Location+Category
knowledge system -- see app/db/models/category_knowledge.py).

Same shape and same reasoning as app/services/knowledge_type_policy.py's
enum-only resolution for dynamically-created KnowledgeTypeConfig rows: an LLM
may CLASSIFY a piece of knowledge's volatility, but it never supplies a raw
number of days/hours. Every duration below is computed HERE, from a small,
fixed enumeration, by code the model cannot influence -- if the model returns
a class that isn't one of these five, resolution rejects the proposal rather
than guessing a duration.

THE FIVE CLASSES, why these durations:

VERY_HIGH -- real-time physical state ("is it open right now", "is it
             currently crowded"). Anchored on the low end of
             KnowledgeTypeConfig's own existing hazard windows (weather: 6h,
             snow_ice: 24h) so the two systems don't invent two incompatible
             fast timescales -- this band deliberately overlaps with the
             retained hazard subsystem (see knowledge_types.py's
             active-type gating) rather than trying to replace it.
HIGH      -- changes on a business/seasonal cadence (temporary closures,
             seasonal hours, current pricing, a special event this week).
             Anchored on KnowledgeTypeConfig's obstruction window (168h/7d).
MEDIUM    -- changes with normal turnover but not daily (facilities,
             regular menu highlights, typical crowd pattern, staff
             recommendations). Below KnowledgeTypeConfig's range entirely --
             this is most of what general Location knowledge actually is.
LOW       -- changes rarely, tied to ongoing identity (what a place is
             generally known for, typical visitor experience, atmosphere).
VERY_LOW  -- effectively permanent (historical facts, founding story,
             architectural/geographic/cultural facts). A large but finite
             number, not "never" -- avoids an infinite-duration special case
             everywhere freshness math happens.
"""

VOLATILITY_CLASSES = ("VERY_HIGH", "HIGH", "MEDIUM", "LOW", "VERY_LOW")

# class -> freshness_duration_hours. Snapshotted onto CategoryKnowledge at
# creation time (see services/category_knowledge.py) -- never re-read live,
# so changing this table only affects knowledge created AFTER the change.
VOLATILITY_DURATIONS_HOURS: dict[str, int] = {
    "VERY_HIGH": 24,          # 1 day
    "HIGH": 24 * 7,           # 7 days
    "MEDIUM": 24 * 45,        # ~6 weeks
    "LOW": 24 * 270,          # ~9 months
    "VERY_LOW": 24 * 365 * 3,  # 3 years
}

DEFAULT_VOLATILITY = "MEDIUM"


class InvalidVolatilityError(Exception):
    """Raised when a proposed volatility class isn't one of the five fixed
    values. `message` is always safe to persist/show."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def resolve_freshness_duration_hours(volatility: str) -> int:
    """Maps a volatility class to its deterministic duration. Raises
    InvalidVolatilityError for anything outside the fixed enum -- never
    guesses a fallback duration for an unrecognized value."""
    if volatility not in VOLATILITY_DURATIONS_HOURS:
        raise InvalidVolatilityError(f"Unknown volatility class: {volatility!r}")
    return VOLATILITY_DURATIONS_HOURS[volatility]
