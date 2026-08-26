"""Domain prompt/tool-schema construction for LLM structured extraction (Step 9),
kept separate from app/services/extraction/anthropic_provider.py's actual API
call so the provider module stays a thin, swappable transport layer -- none of
this module imports the anthropic SDK.
"""

from app.db.models.knowledge_type_config import KnowledgeTypeConfig
from app.schemas.geographic_context import NearestKnownPlace

# The tool name is also matched against in anthropic_provider.py when reading
# back the forced tool_use block -- keep both in sync.
EXTRACTION_TOOL_NAME = "record_observations"

SYSTEM_PROMPT = """You convert a trail guide's raw field report into zero or more structured observations for a hiking-trail knowledge base.

Rules:
1. Extract only information the guide actually stated or strongly implied in the text below -- never invent details.
2. Do not invent weather, trail conditions, places, dates, quantities, or risks that are not in the text.
3. Do not convert the guide's uncertainty into false certainty -- if they were unsure or vague, keep the value/evidence appropriately hedged.
4. It is correct to return zero observations if the text contains nothing useful for the allowed knowledge types.
5. Only use knowledge_type values from the allowed list you are given. Never invent a knowledge_type that isn't in that list.
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
"""


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
            "guide's field report."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "observations": {
                    "type": "array",
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
            },
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
