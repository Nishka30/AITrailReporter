"""Deterministic policy for turning a MODEL-PROPOSED knowledge category into a
real KnowledgeTypeConfig row (Step 16).

This module exists to answer one question safely: when Explore surfaces a
genuinely new, reusable category of trail knowledge (e.g. "parking
availability"), what freshness window, aging threshold, relevance radius,
priority, and safety flag should it get?

THE MODEL IS NEVER THE DATABASE AUTHORITY. The extraction provider may only
SELECT one value from each of three small, fixed, application-owned
enumerations (volatility / scope / significance). It can never supply a
number, a boolean, or a policy value of any kind. Every numeric column on the
resulting row is computed HERE, from those enum choices, by code the model
cannot influence. If the model returns an enum value that isn't in these
tables, validation rejects the whole proposal rather than falling back to a
guess.

The numbers below are anchored to the four hand-seeded types that already
shipped (see alembic f73d25cbe979_seed_example_knowledge_type_configs):
  weather          6h / 3h  / 10000m / priority 5 / safety-critical
  trail_condition  72h / 24h / 2000m / priority 4
  snow_ice         24h / 12h / 2000m / priority 5 / safety-critical
  obstruction      168h / 72h / 500m / priority 4 / safety-critical
so a dynamically created type lands in the same value space as a hand-tuned
one rather than in an invented parallel scale.
"""

import re

# --- volatility -> (freshness_window_hours, aging_threshold_hours) ----------
# "How quickly does this kind of information stop being trustworthy?"
# 'hours' is anchored on the seeded `weather` row; 'days' on `trail_condition`.
# 'weeks'/'months' extend the same scale for the slower-moving categories
# Explore is most likely to surface (facilities, access rules, cultural
# context) -- deliberately generous, because wrongly marking durable
# information stale generates pointless questions.
VOLATILITY_PROFILES: dict[str, tuple[int, int]] = {
    "hours": (6, 3),
    "days": (72, 24),
    "weeks": (336, 168),
    "months": (2160, 720),
}

# --- scope -> geographic_relevance_radius_meters ----------------------------
# "How far from where it was observed does this information still apply?"
# Anchored on the seeded rows: obstruction 500m (a specific blockage),
# trail_condition/snow_ice 2000m (a stretch of trail), weather 10000m (a
# whole valley).
SCOPE_PROFILES: dict[str, int] = {
    "point": 500,
    "local": 2000,
    "area": 10000,
}

# --- significance -> (safety_critical, default_priority) --------------------
# default_priority follows the direction already documented in
# app/services/knowledge_decisions.py (HIGHER == more important). Values stay
# inside the 0-5 band the seed rows use.
#
# NOTE the deliberate ceiling: a dynamically created type can reach
# safety_critical=True, because a genuine safety category (e.g. "rockfall
# risk") surfacing through Explore SHOULD outrank enrichment content. It is
# capped at priority 5, the same ceiling the hand-seeded safety types use --
# a model-proposed type can never outrank a human-configured one.
SIGNIFICANCE_PROFILES: dict[str, tuple[bool, int]] = {
    "safety": (True, 5),
    "practical": (False, 3),
    "enrichment": (False, 1),
}

# Hard cap on how many brand-new knowledge types ONE extraction may create.
# Blast-radius control: this module can validate a proposal's STRUCTURE, but
# it cannot semantically judge whether a category is genuinely reusable (see
# backend/README.md's honest statement of this limitation). Capping the count
# means a single misbehaving or over-eager extraction can add at most this
# many rows, not an unbounded spray.
MAX_NEW_TYPES_PER_EXTRACTION = 2

# Structural rules for a machine-safe knowledge_type name. Mirrors the shape
# of the existing seeded names (snake_case, lowercase ASCII, no digits-only
# segments) so dynamically created types are indistinguishable in form from
# hand-written ones.
_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")
_MAX_NAME_LENGTH = 100  # matches KnowledgeTypeConfig.knowledge_type's String(100)
_MAX_DISPLAY_NAME_LENGTH = 255  # matches KnowledgeTypeConfig.display_name

# Categories that must never be auto-created because a hand-tuned equivalent
# already exists or is reserved. Normalization can produce these from a
# near-miss proposal (e.g. "weather_conditions" -> "weather_conditions", which
# is NOT this list, but "weather" would be) -- the existing-type lookup in
# knowledge_types.py already catches exact matches; this is a second, explicit
# guard for the four shipped types so a model can never redefine them even if
# one were somehow deactivated.
RESERVED_TYPE_NAMES = frozenset({"weather", "trail_condition", "snow_ice", "obstruction"})


class InvalidKnowledgeTypeProposalError(Exception):
    """Raised when a proposed knowledge type fails structural or policy
    validation. `message` is always safe to persist and show -- it describes
    the shape violation, never raw model output beyond the offending value."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def normalize_type_name(raw: str) -> str:
    """Deterministic normalization of a model-proposed name into the
    snake_case form this database uses. Lowercases, converts separators and
    whitespace to underscores, strips anything outside [a-z0-9_], and collapses
    repeated/leading/trailing underscores.

    Normalization is what makes duplicate detection meaningful: "Parking
    Availability", "parking-availability", and "parking availability" all
    collapse to the single name `parking_availability`, so the
    existing-type lookup in create_or_get_dynamic_type() sees them as the same
    category instead of creating three near-identical rows.

    Raises InvalidKnowledgeTypeProposalError if nothing valid survives -- never
    returns a fabricated or truncated-to-garbage name.
    """
    lowered = raw.strip().lower()
    # Separators -> underscore, then drop every remaining disallowed character
    # (rather than substituting it, which could fuse unrelated words).
    underscored = re.sub(r"[\s\-/.]+", "_", lowered)
    cleaned = re.sub(r"[^a-z0-9_]", "", underscored)
    collapsed = re.sub(r"_+", "_", cleaned).strip("_")

    if not collapsed:
        raise InvalidKnowledgeTypeProposalError(
            "Proposed knowledge type name contained no usable characters."
        )
    if len(collapsed) > _MAX_NAME_LENGTH:
        raise InvalidKnowledgeTypeProposalError(
            f"Proposed knowledge type name exceeds {_MAX_NAME_LENGTH} characters."
        )
    if not _NAME_RE.match(collapsed):
        # Reachable when the name starts with a digit -- the character filter
        # above can't fix that, and silently prefixing something would be
        # inventing a name the model never proposed.
        raise InvalidKnowledgeTypeProposalError(
            f"Proposed knowledge type name is not a valid identifier: {collapsed!r}"
        )
    # NOTE: the reserved-name check deliberately does NOT live here. This
    # function is a pure structural normalizer, and callers must be able to
    # normalize a name in order to look it up among the existing active types
    # BEFORE any policy judgement is applied -- otherwise a proposal that simply
    # rediscovers an already-seeded category (Case A) would be rejected instead
    # of being recorded against that existing type. See resolve_policy, which
    # applies the reserved check at the point where a NEW row would actually be
    # created.
    return collapsed


def normalize_display_name(raw: str, fallback_type_name: str) -> str:
    """Human-readable label for the new type. Whitespace-collapsed and length-
    capped; falls back to a Title Cased version of the normalized machine name
    if the model supplied nothing usable -- a deterministic derivation from a
    value that already passed validation, not an invented string."""
    collapsed = re.sub(r"\s+", " ", raw.strip())
    if not collapsed:
        return fallback_type_name.replace("_", " ").title()
    return collapsed[:_MAX_DISPLAY_NAME_LENGTH]


class ResolvedTypePolicy:
    """The complete, deterministically-computed set of column values for a new
    KnowledgeTypeConfig row. Every field here came from this module's tables --
    none of them came from the model."""

    __slots__ = (
        "knowledge_type",
        "display_name",
        "freshness_window_hours",
        "aging_threshold_hours",
        "geographic_relevance_radius_meters",
        "default_priority",
        "safety_critical",
    )

    def __init__(
        self,
        knowledge_type: str,
        display_name: str,
        freshness_window_hours: int,
        aging_threshold_hours: int,
        geographic_relevance_radius_meters: int,
        default_priority: int,
        safety_critical: bool,
    ):
        self.knowledge_type = knowledge_type
        self.display_name = display_name
        self.freshness_window_hours = freshness_window_hours
        self.aging_threshold_hours = aging_threshold_hours
        self.geographic_relevance_radius_meters = geographic_relevance_radius_meters
        self.default_priority = default_priority
        self.safety_critical = safety_critical


def resolve_policy(
    raw_name: str, raw_display_name: str, volatility: str, scope: str, significance: str
) -> ResolvedTypePolicy:
    """Maps a validated proposal onto concrete column values. The three enum
    arguments MUST be exact keys of the profile tables above -- an unrecognized
    value raises rather than defaulting, so a model that invents an enum value
    can never silently land a row with guessed policy numbers."""
    knowledge_type = normalize_type_name(raw_name)

    # Applied HERE rather than in normalize_type_name: by the time resolve_policy
    # is called, the caller has already established that this name does not
    # match an existing ACTIVE type (that's Case A and is handled before this
    # point). So reaching here with a reserved name means the model is trying to
    # (re)define one of the four hand-seeded categories that is currently
    # inactive -- which must never happen automatically.
    if knowledge_type in RESERVED_TYPE_NAMES:
        raise InvalidKnowledgeTypeProposalError(
            f"Proposed knowledge type name is reserved: {knowledge_type!r}"
        )

    display_name = normalize_display_name(raw_display_name, knowledge_type)

    if volatility not in VOLATILITY_PROFILES:
        raise InvalidKnowledgeTypeProposalError(
            f"Unknown volatility profile: {volatility!r}"
        )
    if scope not in SCOPE_PROFILES:
        raise InvalidKnowledgeTypeProposalError(f"Unknown scope profile: {scope!r}")
    if significance not in SIGNIFICANCE_PROFILES:
        raise InvalidKnowledgeTypeProposalError(
            f"Unknown significance profile: {significance!r}"
        )

    freshness_window_hours, aging_threshold_hours = VOLATILITY_PROFILES[volatility]
    safety_critical, default_priority = SIGNIFICANCE_PROFILES[significance]

    return ResolvedTypePolicy(
        knowledge_type=knowledge_type,
        display_name=display_name,
        freshness_window_hours=freshness_window_hours,
        aging_threshold_hours=aging_threshold_hours,
        geographic_relevance_radius_meters=SCOPE_PROFILES[scope],
        default_priority=default_priority,
        safety_critical=safety_critical,
    )
