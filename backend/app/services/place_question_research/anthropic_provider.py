"""The ONLY file that imports the anthropic SDK for popular-question research
(Step 18) -- same isolation as app/services/extraction/anthropic_provider.py
and app/services/question_generation/anthropic_provider.py. Reuses the SAME
Anthropic key/model configuration as both; no new secret, and the mobile app
never holds a search or model credential of any kind.

This is the only provider in the codebase that uses a SERVER tool
(`web_search`), which runs on Anthropic's infrastructure rather than here.
Two consequences the other two providers don't have to deal with, both handled
below:

  - `stop_reason == "pause_turn"`: a long server-tool turn can pause and must
    be resumed by re-sending the conversation. Capped, so a pathological loop
    can't run forever.
  - A failed search returns HTTP 200 with an ERROR block, not an exception --
    and on error the block's `content` is an object rather than the usual
    list. Checked explicitly; a search failure degrades to "no information
    found" (zero questions), never to invented ones.

Structured output uses `output_config.format` rather than the forced
tool_choice the other two providers use: tool_choice cannot be pinned to a
custom tool while a server tool also needs to be free to run.
"""

import json
import logging

import anthropic

from app.core.config import settings
from app.services.place_question_research.prompt import (
    OUTPUT_SCHEMA,
    RESEARCH_TOOL_MAX_SEARCHES,
    SYSTEM_PROMPT,
    build_user_message,
)

logger = logging.getLogger(__name__)

# How many times a paused turn may be resumed before giving up.
_MAX_PAUSE_RESUMES = 3

# The dynamic-filtering web search tool. Requires Opus 4.6+/Sonnet 4.6+; the
# configured default model (claude-sonnet-5) supports it.
_WEB_SEARCH_TOOL = {
    "type": "web_search_20260209",
    "name": "web_search",
    "max_uses": RESEARCH_TOOL_MAX_SEARCHES,
}


class PlaceQuestionResearchProviderError(Exception):
    """Raised for any failure that prevents usable structured output. `message`
    is always safe to persist and show -- no API key, no raw provider
    internals."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _get_client() -> anthropic.Anthropic:
    if not settings.anthropic_api_key:
        raise PlaceQuestionResearchProviderError(
            "Question research service is not configured on the server."
        )
    return anthropic.Anthropic(
        api_key=settings.anthropic_api_key,
        # Deliberately NOT anthropic_request_timeout_seconds: this request runs
        # real web searches server-side before it generates anything, so it is
        # in a different latency class from every other LLM call here. See the
        # setting's comment in app/core/config.py.
        timeout=settings.place_question_research_timeout_seconds,
    )


def _log_search_outcomes(response) -> None:
    """Records whether the server-side searches actually succeeded. Purely
    diagnostic -- a search failure is not fatal here, it simply means less
    information was available, which the model is instructed to report as
    found_information=false rather than compensate for."""
    for block in response.content:
        if getattr(block, "type", None) != "web_search_tool_result":
            continue
        content = getattr(block, "content", None)
        # On error this is an object with .error_code; on success it's a list
        # of results. Branching before indexing is required.
        if isinstance(content, list):
            logger.info("web_search returned %d results.", len(content))
        else:
            logger.warning(
                "web_search failed: %s", getattr(content, "error_code", "unknown_error")
            )


def _extract_json(response) -> dict:
    for block in response.content:
        if getattr(block, "type", None) == "text":
            text = block.text.strip()
            if not text:
                continue
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise PlaceQuestionResearchProviderError(
                    "Question research service did not return valid structured output."
                ) from exc
            if isinstance(parsed, dict):
                return parsed
    raise PlaceQuestionResearchProviderError(
        "Question research service did not return structured output."
    )


def research_place_questions(
    place_name: str,
    latitude: float,
    longitude: float,
    description: str | None,
) -> dict:
    """Runs one web-research request and returns the raw structured output
    dict UNVALIDATED -- validation.py is responsible for never letting this
    reach PostgreSQL unchecked. Raises PlaceQuestionResearchProviderError on
    any failure; never fabricates a result."""
    client = _get_client()
    messages = [
        {
            "role": "user",
            "content": build_user_message(place_name, latitude, longitude, description),
        }
    ]

    resumes = 0
    while True:
        try:
            response = client.messages.create(
                model=settings.anthropic_model,
                max_tokens=settings.anthropic_max_output_tokens,
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=[_WEB_SEARCH_TOOL],
                output_config={"format": OUTPUT_SCHEMA},
            )
        except anthropic.APIStatusError as exc:
            logger.warning("Anthropic API error (place question research): status=%s", exc.status_code)
            raise PlaceQuestionResearchProviderError(
                f"Question research request failed (status {exc.status_code})."
            ) from exc
        except Exception as exc:
            logger.warning(
                "Anthropic request failed (place question research): %s", type(exc).__name__
            )
            raise PlaceQuestionResearchProviderError(
                "Could not reach the question research service."
            ) from exc

        if response.stop_reason != "pause_turn":
            break

        resumes += 1
        if resumes > _MAX_PAUSE_RESUMES:
            raise PlaceQuestionResearchProviderError(
                "Question research did not finish in time."
            )
        # Resume the paused turn by appending it and re-sending.
        messages.append({"role": "assistant", "content": response.content})

    _log_search_outcomes(response)
    return _extract_json(response)
