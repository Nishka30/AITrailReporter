"""The ONLY file that imports the anthropic SDK for question generation (Step
12) -- mirrors the isolation of app/services/extraction/anthropic_provider.py.
Reuses the SAME Anthropic configuration/key as extraction (Step 9) --
`settings.anthropic_api_key`/`anthropic_model` -- no separate key, no new
config surface.
"""

import logging

import anthropic

from app.core.config import settings
from app.services.question_generation.prompt import (
    QUESTION_TOOL_NAME,
    SYSTEM_PROMPT,
    build_question_tool,
    build_user_message,
)

logger = logging.getLogger(__name__)


class QuestionGenerationProviderError(Exception):
    """Raised for any failure that prevents usable structured output -- missing
    config, auth, network, provider-side error, or a response that didn't come
    back as the forced tool call at all. `message` is always safe to persist
    and show (no API key, no raw provider internals beyond a short, safe
    description)."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _get_client() -> anthropic.Anthropic:
    if not settings.anthropic_api_key:
        raise QuestionGenerationProviderError(
            "Question generation service is not configured on the server."
        )
    return anthropic.Anthropic(
        api_key=settings.anthropic_api_key,
        timeout=settings.anthropic_request_timeout_seconds,
    )


def generate_question_text(
    display_name: str,
    gap_state: str,
    staleness_severity_hours: float,
    nearest_known_place_name: str | None,
    nearest_known_place_distance_meters: float | None,
) -> dict:
    """Sends one question-generation request to Claude (client.messages.create
    -- the same real installed SDK method used by extraction) with tool_choice
    forced to generate_guide_question. Returns the tool call's raw `input`
    dict UNVALIDATED -- app/services/question_generation/validation.py is
    responsible for never letting this reach PostgreSQL without validation.
    Raises QuestionGenerationProviderError on any failure; never fabricates a
    result."""
    client = _get_client()
    tool = build_question_tool()
    user_message = build_user_message(
        display_name, gap_state, staleness_severity_hours,
        nearest_known_place_name, nearest_known_place_distance_meters,
    )

    try:
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_output_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            tools=[tool],
            tool_choice={"type": "tool", "name": QUESTION_TOOL_NAME},
        )
    except anthropic.APIStatusError as exc:
        logger.warning("Anthropic API error (question generation): status=%s", exc.status_code)
        raise QuestionGenerationProviderError(
            f"Question generation request failed (status {exc.status_code})."
        ) from exc
    except Exception as exc:
        logger.warning("Anthropic request failed (question generation): %s", type(exc).__name__)
        raise QuestionGenerationProviderError(
            "Could not reach the question generation service."
        ) from exc

    for block in response.content:
        if block.type == "tool_use" and block.name == QUESTION_TOOL_NAME:
            return block.input

    raise QuestionGenerationProviderError(
        "Question generation service did not return structured output."
    )
