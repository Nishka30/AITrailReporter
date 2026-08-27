"""Domain prompt/tool-schema construction for LLM structured extraction (Step 9),
kept separate from app/services/extraction/anthropic_provider.py's actual API
call so the provider module stays a thin, swappable transport layer -- none of
this module imports the anthropic SDK.
"""

from app.db.models.knowledge_type_config import KnowledgeTypeConfig
from app.schemas.geographic_context import NearestKnownPlace
from app.services.knowledge_type_policy import (
    MAX_NEW_TYPES_PER_EXTRACTION,
    SCOPE_PROFILES,
    SIGNIFICANCE_PROFILES,
    VOLATILITY_PROFILES,
)

# The tool name is also matched against in anthropic_provider.py when reading
# back the forced tool_use block -- keep both in sync.
EXTRACTION_TOOL_NAME = "record_observations"

SYSTEM_PROMPT = """You convert a trail guide's raw field report into zero or more structured observations for a hiking-trail knowledge base.

Rules:
1. Extract only information the guide actually stated or strongly implied in the text below -- never invent details.
2. Do not invent weather, trail conditions, places, dates, quantities, or risks that are not in the text.
3. Do not convert the guide's uncertainty into false certainty -- if they were unsure or vague, keep the value/evidence appropriately hedged.
4. It is correct to return zero observations if the text contains nothing useful.
5. For the `observations` array, only use knowledge_type values from the allowed list you are given. Never invent a knowledge_type there.
6. Always answer only through the record_observations tool -- never as plain conversational text.
7. If the report describes multiple distinct conditions, return them as separate observations rather than merging them into one.
8. Preserve the guide's own uncertainty in value/evidence rather than smoothing it away into a confident-sounding statement.
9. Do not infer a specific location, coordinates, or place name from general geographic knowledge -- location is attached separately by the system, not by you. Any location context you are given is background only.
10. You are not writing a trip report or a conversational reply -- only structured extraction data.

For each observation you record:
- knowledge_type: exactly one of the allowed types given to you.
- value: a small, flat JSON object describing the condition, using reasonable field names of your own choosing (for example condition, severity, caution_required) appropriate to that knowledge_type -- grounded only in the text, never fabricated.
- confidence: your own confidence that this observation is an accurate extraction from the text, from 0.0 to 1.0. This is your extraction confidence, not a claim about objective ground truth.
- evidence: a short quote or close paraphrase from the source text that grounds this observation. Never invent evidence that isn't in the text.

PROPOSING A NEW CATEGORY (the `new_knowledge_types` array)

Sometimes a report contains genuinely useful trail knowledge that does not fit ANY allowed knowledge type. In that case you may propose a new category, but only under a strict test.

The test -- ALL of these must be true:
- It is a REUSABLE CATEGORY, not a one-off fact. The system must be able to sensibly ask a different guide about this same category at this or another location in the future.
- It is about the PLACE or the CONDITIONS there -- something a future traveller or guide would benefit from knowing.
- It is not already covered by one of the allowed types. Prefer an allowed type whenever one reasonably fits; only propose new when none does.

Good proposals (reusable, place-centred, askable again):
- parking_availability -- "Parking near the lake fills up before noon."
- water_source -- "The spring by the third bridge is running clear."
- mobile_signal -- "No signal at all past the second ridge."

Bad proposals -- DO NOT propose these; leave them out entirely:
- Personal or one-off events: "I drank tea at 4 PM", "my boots got wet", "we started late".
- Someone's opinion or mood rather than a condition of the place.
- A category so narrow it could never apply anywhere else.
- A near-synonym of an allowed type (use the allowed type instead).

If the useful information fits an allowed type, put it in `observations`. If nothing fits and the strict test above passes, put it in `new_knowledge_types`. If neither applies, return both arrays empty -- that is a correct, expected answer, and it is much better than inventing a category.

For each new category you propose, you also supply the observation that goes with it, plus three CLASSIFICATION choices. You are choosing a descriptive bucket, not configuring the system -- the actual freshness/radius/priority numbers are decided by the application, not by you:
- volatility: how quickly this kind of information stops being trustworthy.
- scope: how far from where it was observed the information still applies.
- significance: whether this is a safety matter, practical trip-planning information, or enrichment.

Never propose more than {max_new_types} new categories in one response.
""".format(max_new_types=MAX_NEW_TYPES_PER_EXTRACTION)

# Human-readable one-liners for each enum value, rendered into the tool schema
# description so the model picks a bucket by MEANING rather than guessing what
# a bare token like "weeks" is supposed to imply. The application still owns
# the numbers these map to (see knowledge_type_policy.py) -- these strings only
# steer the choice.
_VOLATILITY_HINTS = {
    "hours": "changes within hours (weather-like)",
    "days": "changes over a few days (trail surface, conditions)",
    "weeks": "changes over weeks (facilities, seasonal access, supplies)",
    "months": "rarely changes (cultural context, permanent features, local customs)",
}
_SCOPE_HINTS = {
    "point": "applies only at one specific spot",
    "local": "applies across a village, trailhead, or stretch of trail",
    "area": "applies across a whole valley or region",
}
_SIGNIFICANCE_HINTS = {
    "safety": "affects someone's physical safety",
    "practical": "useful for planning a trip, but not a safety matter",
    "enrichment": "interesting or culturally valuable context",
}


def _enum_description(label: str, hints: dict[str, str], keys) -> str:
    joined = "; ".join(f"'{key}' = {hints[key]}" for key in keys if key in hints)
    return f"{label}: {joined}."


def build_extraction_tool(allowed_type_names: list[str]) -> dict:
    """JSON-schema tool definition. The knowledge_type enum is built from the
    SAME allowed-types list passed into the prompt, so the provider is steered
    toward never emitting a value outside it.

    Deliberately NOT using the SDK's `strict: True` tool mode: Anthropic's
    strict validation requires every object-typed schema node to declare
    `additionalProperties: false` explicitly (confirmed against the real API --
    a `strict: True` version of this exact schema was rejected with HTTP 400,
    "For 'object' type, 'additionalProperties' must be explicitly set to
    false"). That's incompatible with `value` being an intentionally
    open-ended JSON object whose field names the LLM chooses per observation
    (see Part 6 of the spec: "value must be structured JSON" -- not a fixed
    per-type schema). Since provider output must NEVER be trusted directly
    either way, the real enforcement is app/services/extraction/validation.py's
    Pydantic validation after the call returns, not this schema -- this schema
    only steers the model, it is not the safety boundary."""
    return {
        "name": EXTRACTION_TOOL_NAME,
        "description": (
            "Record zero or more structured observations extracted from a "
            "guide's field report, and optionally propose genuinely new, "
            "reusable knowledge categories the report revealed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "observations": {
                    "type": "array",
                    "description": (
                        "Observations that fit one of the ALLOWED knowledge types."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "knowledge_type": {
                                "type": "string",
                                "enum": allowed_type_names,
                            },
                            "value": {"type": "object"},
                            "confidence": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1,
                            },
                            "evidence": {"type": "string"},
                        },
                        "required": ["knowledge_type", "value", "confidence", "evidence"],
                        "additionalProperties": False,
                    },
                },
                # Separate array, NOT a magic value inside `observations`: the
                # two go down materially different code paths (one resolves an
                # existing id, one creates a row), and keeping them apart in
                # the schema means a malformed proposal can never be mistaken
                # for an ordinary observation.
                "new_knowledge_types": {
                    "type": "array",
                    "description": (
                        "Genuinely new, REUSABLE categories that no allowed type "
                        "covers. Must pass the strict test in the system prompt. "
                        "Leave empty unless it clearly passes -- empty is the "
                        "normal, correct answer."
                    ),
                    "maxItems": MAX_NEW_TYPES_PER_EXTRACTION,
                    "items": {
                        "type": "object",
                        "properties": {
                            "knowledge_type": {
                                "type": "string",
                                "description": (
                                    "Proposed machine name in lower snake_case, "
                                    "e.g. parking_availability."
                                ),
                            },
                            "display_name": {
                                "type": "string",
                                "description": "Short human-readable label, e.g. Parking Availability.",
                            },
                            "volatility": {
                                "type": "string",
                                "enum": list(VOLATILITY_PROFILES.keys()),
                                "description": _enum_description(
                                    "How quickly this information goes out of date",
                                    _VOLATILITY_HINTS,
                                    VOLATILITY_PROFILES.keys(),
                                ),
                            },
                            "scope": {
                                "type": "string",
                                "enum": list(SCOPE_PROFILES.keys()),
                                "description": _enum_description(
                                    "How far the information applies",
                                    _SCOPE_HINTS,
                                    SCOPE_PROFILES.keys(),
                                ),
                            },
                            "significance": {
                                "type": "string",
                                "enum": list(SIGNIFICANCE_PROFILES.keys()),
                                "description": _enum_description(
                                    "What kind of value this has",
                                    _SIGNIFICANCE_HINTS,
                                    SIGNIFICANCE_PROFILES.keys(),
                                ),
                            },
                            "value": {"type": "object"},
                            "confidence": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1,
                            },
                            "evidence": {"type": "string"},
                        },
                        "required": [
                            "knowledge_type",
                            "display_name",
                            "volatility",
                            "scope",
                            "significance",
                            "value",
                            "confidence",
                            "evidence",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
            # `new_knowledge_types` is deliberately NOT required: an older or
            # more conservative response that omits it entirely is valid and
            # means "no proposals" (validation defaults it to an empty list),
            # so this change cannot break the existing extraction contract.
            "required": ["observations"],
            "additionalProperties": False,
        },
    }


def build_user_message(
    source_text: str,
    allowed_types: list[KnowledgeTypeConfig],
    nearest_known_place: NearestKnownPlace | None,
) -> str:
    type_lines = "\n".join(f"- {t.knowledge_type}: {t.display_name}" for t in allowed_types)

    if nearest_known_place is not None:
        location_line = (
            f"Approximate location context: near '{nearest_known_place.name}' "
            f"(~{round(nearest_known_place.distance_meters)}m away). This is "
            "background context only -- do not output coordinates or place "
            "names yourself."
        )
    else:
        location_line = "Approximate location context: not available."

    return (
        "Allowed knowledge types:\n"
        f"{type_lines}\n\n"
        f"{location_line}\n\n"
        "Guide's field report:\n"
        f"{source_text}"
    )
