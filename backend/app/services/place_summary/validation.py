"""Validates raw place-summary generation output before anything reaches
PostgreSQL -- mirrors place_question_research/validation.py's citation
allowlist, since this feature is subject to the exact same anti-hallucination
requirement: a URL the model returns is a CLAIM about provenance, not
provenance, until checked against what was genuinely retrieved.
"""

import logging

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

MAX_DESCRIPTION_LENGTH = 2000
MAX_KNOWN_FOR_LENGTH = 500
MAX_LIST_ITEM_LENGTH = 500
MAX_LIST_ITEMS = 12
MAX_PRACTICAL_INFO_LENGTH = 2000


def _clean_str_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned = []
    for v in values:
        if isinstance(v, str) and v.strip():
            cleaned.append(v.strip()[:MAX_LIST_ITEM_LENGTH])
    return cleaned[:MAX_LIST_ITEMS]


class PlaceSummaryOutput(BaseModel):
    found_information: bool
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)
    known_for: str | None = Field(default=None, max_length=MAX_KNOWN_FOR_LENGTH)
    highlights: list[str] = Field(default_factory=list)
    things_to_do: list[str] = Field(default_factory=list)
    important_facts: list[str] = Field(default_factory=list)
    practical_info: str | None = Field(default=None, max_length=MAX_PRACTICAL_INFO_LENGTH)
    warnings: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)


class PlaceSummaryValidationError(Exception):
    """The response was not the agreed shape at all."""


class ValidatedPlaceSummary(BaseModel):
    description: str | None = None
    known_for: str | None = None
    highlights: list[str] = Field(default_factory=list)
    things_to_do: list[str] = Field(default_factory=list)
    important_facts: list[str] = Field(default_factory=list)
    practical_info: str | None = None
    warnings: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)


def validate_summary_output(
    raw: dict, allowed_urls: set[str]
) -> ValidatedPlaceSummary | None:
    """Returns a cleaned, citation-checked summary, or None when the model
    reported nothing usable (a legitimate, honest outcome -- most places are
    not written about) or the response failed validation entirely.

    `allowed_urls` is every source URL genuinely retrieved while researching
    this place (the same set place_questions.ensure_researched already builds
    for question grounding). A returned URL not in this set is dropped rather
    than stored -- see place_question_research/validation.py's identical
    rule and rationale.
    """
    if not isinstance(raw, dict):
        raise PlaceSummaryValidationError("Summary output was not an object.")

    try:
        parsed = PlaceSummaryOutput.model_validate(raw)
    except ValidationError as exc:
        raise PlaceSummaryValidationError(
            f"Summary output had an unexpected shape: {exc.error_count()} errors"
        )

    if not parsed.found_information:
        return None

    kept_urls = [u for u in parsed.source_urls if u in allowed_urls]
    if not kept_urls:
        # No traceable basis -- exactly like an uncited invitation, this is
        # dropped rather than stored uncited (see
        # place_question_research/validation.py's _keep_only_cited_urls).
        logger.info("Dropped a generated place summary with no citations in the research.")
        return None

    return ValidatedPlaceSummary(
        description=parsed.description.strip() if parsed.description else None,
        known_for=parsed.known_for.strip() if parsed.known_for else None,
        highlights=_clean_str_list(parsed.highlights),
        things_to_do=_clean_str_list(parsed.things_to_do),
        important_facts=_clean_str_list(parsed.important_facts),
        practical_info=parsed.practical_info.strip() if parsed.practical_info else None,
        warnings=_clean_str_list(parsed.warnings),
        source_urls=kept_urls,
    )
