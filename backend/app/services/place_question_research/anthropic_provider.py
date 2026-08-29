"""The ONLY file that imports the anthropic SDK for place-question generation
-- same isolation as app/services/extraction/anthropic_provider.py and
app/services/question_generation/anthropic_provider.py, reusing the SAME key and
model configuration as both. No new secret, and the mobile app never holds a
model or search credential of any kind.

WHAT CHANGED: this used to run Anthropic's `web_search` server tool and do its
own research. It no longer searches at all. Research arrives already done, as
sourced findings from app/services/research/, and this module's only job is
judgement: which researched details are worth asking a person standing there to
check.

Three things got better by splitting them apart:

  - GROUNDING BECAME CHECKABLE. Every invitation now cites a URL that this
    process actually saw, from a finding stored in the database. Previously the
    grounding lived inside a model call that had already ended.
  - THE CALL GOT ORDINARY. No server tool means no `pause_turn` resumption, no
    HTTP-200-with-an-error-block special case, and no multi-minute latency
    class. This is now a normal single-turn request on the normal timeout.
  - THE JOBS WENT TO THE RIGHT TOOLS. A search product does retrieval; a
    reasoning model does judgement.

SECURITY: the user message contains untrusted web text inside delimited
blocks. The delimiter is stripped from that text before it gets here (at the
provider edge, in research/sanitize.py) so it cannot be forged, and the system
prompt states that block contents are data rather than instructions.
"""

import json
import logging

import anthropic

from app.core.config import settings
from app.services.place_question_research.prompt import (
    OUTPUT_SCHEMA,
    SYSTEM_PROMPT,
    build_user_message,
)

logger = logging.getLogger(__name__)


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
            "Question generation service is not configured on the server."
        )
    return anthropic.Anthropic(
        api_key=settings.anthropic_api_key,
        # The ORDINARY timeout, deliberately. This request no longer runs web
        # searches server-side, so it is no longer in the slow latency class
        # that place_question_research_timeout_seconds exists for -- that
        # setting now covers the research step instead.
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
                raise PlaceQuestionResearchProviderError(
                    "Question generation did not return valid structured output."
                ) from exc
            if isinstance(parsed, dict):
                return parsed
    raise PlaceQuestionResearchProviderError(
        "Question generation did not return structured output."
    )


def generate_place_questions(
    place_name: str,
    latitude: float,
    longitude: float,
    description: str | None,
    locality: str | None,
    findings: list,
    already_asked: list[str],
) -> dict:
    """Turns research findings into invitations.

    Returns the raw structured output dict UNVALIDATED -- validation.py is
    responsible for never letting this reach PostgreSQL unchecked. Raises
    PlaceQuestionResearchProviderError on any failure; never fabricates a
    result.
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
                        place_name,
                        latitude,
                        longitude,
                        description,
                        locality,
                        findings,
                        already_asked,
                    ),
                }
            ],
            output_config={"format": OUTPUT_SCHEMA},
        )
    except anthropic.APIStatusError as exc:
        logger.warning(
            "Anthropic API error (place question generation): status=%s", exc.status_code
        )
        raise PlaceQuestionResearchProviderError(
            f"Question generation request failed (status {exc.status_code})."
        ) from exc
    except Exception as exc:
        logger.warning(
            "Anthropic request failed (place question generation): %s", type(exc).__name__
        )
        raise PlaceQuestionResearchProviderError(
            "Could not reach the question generation service."
        ) from exc

    return _extract_json(response)
