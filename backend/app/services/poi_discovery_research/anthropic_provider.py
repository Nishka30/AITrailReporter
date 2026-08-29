"""The ONLY file that imports the anthropic SDK for POI discovery.

Same isolation and the same server-tool handling as
app/services/place_question_research/anthropic_provider.py -- see that module's
header for why `pause_turn` and web-search error blocks need explicit handling
(a failed search returns HTTP 200 with an error OBJECT where a list of results
would normally be, so the type must be checked before indexing).

Reuses the existing ANTHROPIC_API_KEY. No new secret, no new provider, and the
mobile app never holds a search credential of any kind.
"""

import json
import logging

import anthropic

from app.core.config import settings
from app.services.poi_discovery_research.prompt import (
    DISCOVERY_TOOL_MAX_SEARCHES,
    OUTPUT_SCHEMA,
    SYSTEM_PROMPT,
    build_user_message,
)

logger = logging.getLogger(__name__)

_MAX_PAUSE_RESUMES = 3

_WEB_SEARCH_TOOL = {
    "type": "web_search_20260209",
    "name": "web_search",
    "max_uses": DISCOVERY_TOOL_MAX_SEARCHES,
}


class PoiDiscoveryProviderError(Exception):
    """Any failure that prevents usable structured output. `message` is always
    safe to persist and show -- no API key, no raw provider internals."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _get_client() -> anthropic.Anthropic:
    if not settings.anthropic_api_key:
        raise PoiDiscoveryProviderError("Place discovery is not configured on the server.")
    return anthropic.Anthropic(
        api_key=settings.anthropic_api_key,
        # Web search runs several real searches server-side before generating,
        # so this shares the long place-research timeout rather than the much
        # shorter single-turn one used for extraction.
        timeout=settings.place_question_research_timeout_seconds,
    )


def _log_search_outcomes(response) -> None:
    for block in response.content:
        if getattr(block, "type", None) != "web_search_tool_result":
            continue
        content = getattr(block, "content", None)
        if isinstance(content, list):
            logger.info("web_search returned %d results.", len(content))
        else:
            logger.warning("web_search failed: %s", getattr(content, "error_code", "unknown_error"))


def _extract_json(response) -> dict:
    for block in response.content:
        if getattr(block, "type", None) == "text":
            text = block.text.strip()
            if not text:
                continue
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise PoiDiscoveryProviderError(
                    "Place discovery did not return valid structured output."
                ) from exc
            if isinstance(parsed, dict):
                return parsed
    raise PoiDiscoveryProviderError("Place discovery did not return structured output.")


def discover_places(latitude: float, longitude: float, radius_meters: int) -> dict:
    """Runs one discovery request and returns the raw structured output dict
    UNVALIDATED -- validation.py and poi_discovery.py are jointly responsible
    for never letting this reach PostgreSQL unchecked. Raises
    PoiDiscoveryProviderError on any failure; never fabricates a result."""
    client = _get_client()
    messages = [{"role": "user", "content": build_user_message(latitude, longitude, radius_meters)}]

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
            logger.warning("Anthropic API error (POI discovery): status=%s", exc.status_code)
            raise PoiDiscoveryProviderError(
                f"Place discovery request failed (status {exc.status_code})."
            ) from exc
        except Exception as exc:
            logger.warning("Anthropic request failed (POI discovery): %s", type(exc).__name__)
            raise PoiDiscoveryProviderError("Could not reach the place discovery service.") from exc

        if response.stop_reason != "pause_turn":
            break

        resumes += 1
        if resumes > _MAX_PAUSE_RESUMES:
            raise PoiDiscoveryProviderError("Place discovery did not finish in time.")
        messages.append({"role": "assistant", "content": response.content})

    _log_search_outcomes(response)
    return _extract_json(response)
