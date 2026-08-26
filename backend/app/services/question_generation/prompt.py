"""Domain prompt/tool-schema construction for LLM question generation (Step
12), kept separate from app/services/question_generation/anthropic_provider.py's
actual API call, mirroring app/services/extraction/prompt.py's separation --
none of this module imports the anthropic SDK.
"""

# Also matched against in anthropic_provider.py when reading back the forced
# tool_use block -- keep both in sync.
QUESTION_TOOL_NAME = "generate_guide_question"

SYSTEM_PROMPT = """You write one short, natural question to send to a trek guide out in the field, asking them to check or report on a specific real-world condition.

Rules:
1. Generate exactly one concise, clear question.
2. Ask only about the specific topic and situation described to you below -- nothing else.
3. Do not invent trail conditions, weather, hazards, incidents, closures, landmarks, or any other facts not given to you.
4. Treat any location reference you are given as background only -- it is not proof of any condition, just where to focus the question.
5. If no specific place name is given to you, do not invent one -- refer to "your current location" or similar instead.
6. If the situation says there is currently no report at all, phrase the question as asking the guide to check and report the current situation.
7. If the situation says the last report is out of date, phrase the question as asking for an updated, current condition, referencing that a previous report exists.
8. If the situation says the last report is starting to age but is not yet considered out of date, phrase the question as a light, low-pressure request to confirm or send a quick recent update -- do NOT claim the information is missing or already out of date, since it is not.
9. Make the wording natural and actionable for someone in the field on a phone -- not formal, not robotic.
10. Never mention internal system concepts in your question: do not use words like "knowledge type", "freshness window", "aging", "grace period", "stale", "missing", "confidence score", "database", or "LLM". Write as one person texting a colleague.
11. Respond only through the generate_guide_question tool -- never as plain conversational text.
"""


def build_question_tool() -> dict:
    """JSON-schema tool definition. Deliberately NOT using `strict: True` --
    same reasoning as app/services/extraction/prompt.py: this schema only
    steers the model, app/services/question_generation/validation.py is the
    real safety boundary before anything is persisted."""
    return {
        "name": QUESTION_TOOL_NAME,
        "description": "Record one generated question for a trek guide, plus optional short context.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question_text": {"type": "string"},
                "short_context": {"type": "string"},
            },
            "required": ["question_text"],
            "additionalProperties": False,
        },
    }


def build_user_message(
    display_name: str,
    gap_state: str,
    staleness_severity_hours: float,
    nearest_known_place_name: str | None,
    nearest_known_place_distance_meters: float | None,
) -> str:
    # Three distinct situations (Step 14 adds 'aging' between 'missing' and
    # 'stale') -- each maps to a different tone per SYSTEM_PROMPT rules 6-8:
    # missing -> "check and report" (nothing exists yet); aging -> a light
    # "confirm/quick update" ask (something recent-ish exists, not yet out of
    # date); stale -> "send an updated/current report" (existing report has
    # fully expired). Never conflate aging with missing -- doing so would
    # falsely claim there is no information at all.
    if gap_state == "missing":
        situation = f"There is currently no report at all about {display_name} at this location."
    elif gap_state == "aging":
        situation = (
            f"There is a recent-ish report about {display_name} at this location, but "
            f"it is starting to get old (about {staleness_severity_hours:.0f} hours "
            "past its usual refresh point) and is not yet considered out of date."
        )
    else:
        situation = (
            f"The most recent report about {display_name} at this location is out of "
            f"date (about {staleness_severity_hours:.0f} hours past when it should "
            "have been refreshed)."
        )

    if nearest_known_place_name is not None and nearest_known_place_distance_meters is not None:
        location_line = (
            f"Approximate place name for reference: {nearest_known_place_name} "
            f"(~{round(nearest_known_place_distance_meters)}m away). Background only "
            "-- do not treat this as confirmed information."
        )
    else:
        location_line = "No specific place name is available for this location."

    return f"Topic: {display_name}\n\n{situation}\n\n{location_line}"
