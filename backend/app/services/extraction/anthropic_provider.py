"""The ONLY file that imports the anthropic SDK (Step 9) -- mirrors the
isolation of app/services/transcription/sarvam.py for Sarvam. Nothing outside
this module (and app/services/extractions.py, which only sees the plain dict
this returns) knows or cares which LLM provider is behind extraction.
"""

import logging

import anthropic

from app.core.config import settings
from app.db.models.knowledge_type_config import KnowledgeTypeConfig
from app.schemas.geographic_context import NearestKnownPlace
from app.services.extraction.prompt import (
    EXTRACTION_TOOL_NAME,
    SYSTEM_PROMPT,
    build_extraction_tool,
    build_user_message,
)

logger = logging.getLogger(__name__)


class ExtractionProviderError(Exception):
    """Raised for any failure that prevents usable structured output -- missing
    config, auth, network, provider-side error, or a response that didn't come
    back as the forced tool call at all. `message` is always safe to persist and
    show (no API key, no raw provider internals beyond a short, safe
    description)."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _get_client() -> anthropic.Anthropic:
    if not settings.anthropic_api_key:
        raise ExtractionProviderError("LLM extraction service is not configured on the server.")
    return anthropic.Anthropic(
        api_key=settings.anthropic_api_key,
        timeout=settings.anthropic_request_timeout_seconds,
    )


def extract_observations(
    source_text: str,
    allowed_types: list[KnowledgeTypeConfig],
    nearest_known_place: NearestKnownPlace | None,
) -> dict:
    """Sends one extraction request to Claude (client.messages.create -- the
    actual installed SDK's real method, not assumed) with tool_choice forced to
    the record_observations tool, so the response is guaranteed to be a
    structured tool call rather than free text. Returns the tool call's raw
    `input` dict UNVALIDATED -- app/services/extraction/validation.py is
    responsible for never letting this reach PostgreSQL without domain
    validation. Raises ExtractionProviderError on any failure; never fabricates
    a result."""
    client = _get_client()
    type_names = [t.knowledge_type for t in allowed_types]
    tool = build_extraction_tool(type_names)
    user_message = build_user_message(source_text, allowed_types, nearest_known_place)

    try:
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_output_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            tools=[tool],
            tool_choice={"type": "tool", "name": EXTRACTION_TOOL_NAME},
        )
    except anthropic.APIStatusError as exc:
        # exc.status_code/exc.body may echo request details but never the
        # API key itself -- safe to log and to persist.
        logger.warning("Anthropic API error: status=%s", exc.status_code)
        raise ExtractionProviderError(
            f"LLM extraction request failed (status {exc.status_code})."
        ) from exc
    except Exception as exc:
        # Network failure, DNS failure, timeout, or anything else the SDK's
        # underlying transport raises that isn't a typed APIStatusError.
        # Deliberately logs only the exception TYPE, not str(exc) -- same
        # reasoning as sarvam.py.
        logger.warning("Anthropic request failed: %s", type(exc).__name__)
        raise ExtractionProviderError("Could not reach the LLM extraction service.") from exc

    for block in response.content:
        if block.type == "tool_use" and block.name == EXTRACTION_TOOL_NAME:
            return block.input

    raise ExtractionProviderError("LLM extraction service did not return structured output.")
