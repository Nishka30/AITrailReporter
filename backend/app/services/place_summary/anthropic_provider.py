"""The ONLY file that imports the anthropic SDK for place-summary generation
-- same isolation convention as every other *_provider.py in this codebase
(extraction, question_generation, place_question_research), reusing the same
key and model configuration as all of them. No new secret.
"""

import json
import logging

import anthropic

from app.core.config import settings
from app.services.place_summary.prompt import OUTPUT_SCHEMA, SYSTEM_PROMPT, build_user_message

logger = logging.getLogger(__name__)


class PlaceSummaryProviderError(Exception):
    """Raised for any failure that prevents usable structured output.
    `message` is always safe to persist and show -- no API key, no raw
    provider internals."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _get_client() -> anthropic.Anthropic:
    if not settings.anthropic_api_key:
        raise PlaceSummaryProviderError(
            "Place summary generation service is not configured on the server."
        )
    return anthropic.Anthropic(
        api_key=settings.anthropic_api_key,
        timeout=settings.anthropic_request_timeout_seconds,
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
                raise PlaceSummaryProviderError(
                    "Summary generation did not return valid structured output."
                ) from exc
            if isinstance(parsed, dict):
                return parsed
    raise PlaceSummaryProviderError("Summary generation did not return structured output.")


def generate_place_summary(
    place_name: str,
    latitude: float,
    longitude: float,
    description: str | None,
    locality: str | None,
    findings: list,
    category: str | None = None,
    subcategory: str | None = None,
) -> dict:
    """Turns research findings into a structured place summary.

    Returns the raw structured output dict UNVALIDATED -- validation.py is
    responsible for never letting this reach PostgreSQL unchecked. Raises
    PlaceSummaryProviderError on any failure; never fabricates a result.
    """
    client = _get_client()

    try:
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_output_tokens,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": build_user_message(
                        place_name, latitude, longitude, description, locality,
                        findings, category, subcategory,
                    ),
                }
            ],
            output_config={"format": OUTPUT_SCHEMA},
        )
    except anthropic.APIStatusError as exc:
        logger.warning("Anthropic API error (place summary generation): status=%s", exc.status_code)
        raise PlaceSummaryProviderError(
            f"Summary generation request failed (status {exc.status_code})."
        ) from exc
    except Exception as exc:
        logger.warning("Anthropic request failed (place summary generation): %s", type(exc).__name__)
        raise PlaceSummaryProviderError("Could not reach the summary generation service.") from exc

    return _extract_json(response)
