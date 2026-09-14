"""The constrained model fallback for classifying an ALREADY-IDENTIFIED place.

WHEN THIS RUNS: only when `category_rules.is_weak()` says the deterministic
pass genuinely could not describe the place -- the place_type came out as the
'other' fallback, or it is a reverse-geocoded AREA, or too few informative
themes were implied. Every other place is classified for free, identically
every time, by rules. This is the expensive path, so it is the rare one.

WHAT IT IS NOT ALLOWED TO DO -- the hard boundary:
It classifies a place we have ALREADY identified. It never sees a raw
coordinate and is never asked "what place is this?". Identifying the physical
place from GPS stays entirely with the existing Google/PostGIS pipeline
(poi_discovery.py). By the time anything here runs we know the place's name,
address and provider ids; the only open question is what KIND of place it is.

WHY THE MODEL NEVER EMITS A NUMBER:
It picks slugs from the fixed catalog and a coarse strength word
('defining'/'strong'/'related'). Application code turns those into relevance
and confidence. This is the same discipline knowledge_type_policy.py uses for
LLM-proposed knowledge types, and it exists because a model asked for "a
relevance from 0-100" produces numbers that look precise, vary between runs,
and cannot be reasoned about -- whereas three named strengths are a judgement
a model can actually make consistently, and the mapping to numbers stays
auditable in one place.

The slug lists are enforced as JSON-schema `enum`s, so an invented category
is structurally impossible rather than merely filtered afterwards; the
validation pass is a second belt for anything that still slips through.
"""

import json
import logging

import anthropic

from app.core.config import settings
from app.services.places import category_catalog as catalog
from app.services.places import category_rules

logger = logging.getLogger(__name__)

# Coarse strength -> the numbers application code owns. Deliberately only
# three levels: a model can tell "this is what the place IS FOR" from "this is
# incidentally true of it", but cannot meaningfully distinguish 71 from 78.
STRENGTH_RELEVANCE: dict[str, int] = {
    "defining": 95,
    "strong": 80,
    "related": 65,
}

# One confidence for every AI assignment, below Google's own primaryType
# (0.95) and a curator's written type (0.90), above nothing at all. It
# reflects HOW the claim was established, not how strong the claim is --
# strength is what `relevance` carries.
AI_CONFIDENCE = 0.65

# Hard ceiling on what one classification may assign, enforced after the
# model returns regardless of what it asked for. This is the concrete
# mechanism behind "avoid assigning too many weak or irrelevant categories" --
# without it, a model asked for themes will happily supply a dozen plausible
# ones and the relevance signal becomes noise.
MAX_AI_THEMES = 6


class CategoryClassificationError(Exception):
    """`message` is always safe to log and persist -- no key, no raw provider
    internals."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


SYSTEM_PROMPT = """You classify places for a trail-and-travel knowledge system.

You are given a place that has ALREADY been identified -- its name, where it
is, and whatever the mapping provider recorded about it. Your only job is to
say what KIND of place it is, using a fixed vocabulary.

You are never asked to work out which place a coordinate refers to. That is
already settled before you are called. Do not speculate about location.

Rules:
- Choose exactly one `place_type`: what the place literally IS.
- Choose the themes that genuinely describe it: what it is ABOUT, or what a
  traveller would actually come here for.
- Assign `defining` only to a theme that is a main reason the place matters.
  `strong` means clearly true and significant. `related` means genuinely true
  but secondary.
- Fewer, accurate themes beat many vague ones. A theme that is merely
  technically true is not worth assigning. Most places warrant two to four.
- If you genuinely cannot tell what a place is, choose the `other` place type
  and return no themes. That is a valid, honest answer -- do not guess.
- Base your answer only on the information given. Do not invent facts about
  the place.
"""


def _vocabulary_block() -> str:
    """The catalog, rendered for the prompt. Themes carry their definitions
    (they are abstract, and an undefined theme gets applied inconsistently);
    place types are listed by name only, since their names are concrete."""
    theme_lines = "\n".join(
        f"  {theme.slug} ({theme.display_name}): {theme.description}"
        for theme in catalog.THEMES
        if theme.slug != catalog.OTHER_THEME
    )
    place_type_names = ", ".join(
        place_type.slug
        for place_type in catalog.PLACE_TYPES
        if place_type.slug != catalog.OTHER_PLACE_TYPE
    )
    return (
        f"THEMES (slug, name, meaning):\n{theme_lines}\n\n"
        f"PLACE TYPES (slug):\n  {place_type_names}\n"
    )


def build_user_message(
    *,
    name: str,
    locality: str | None,
    formatted_address: str | None,
    google_primary_type: str | None,
    google_types: list[str] | None,
    description: str | None,
    place_kind: str | None,
) -> str:
    lines = ["THE PLACE (already identified -- classify it, do not re-locate it)"]
    lines.append(f"Name: {name}")
    if locality:
        lines.append(f"Locality: {locality}")
    if formatted_address:
        lines.append(f"Address: {formatted_address}")
    if google_primary_type:
        lines.append(f"Provider primary type: {google_primary_type}")
    if google_types:
        lines.append(f"Provider types: {', '.join(google_types[:12])}")
    if place_kind:
        lines.append(f"Recorded kind: {place_kind}")
    if description:
        lines.append(f"Known description: {description}")
    lines.append("")
    lines.append(_vocabulary_block())
    lines.append(
        "Classify this place. Use only slugs from the vocabulary above."
    )
    return "\n".join(lines)


def _output_schema() -> dict:
    """Enums built from the live catalog, so an invented slug is structurally
    impossible rather than merely rejected after the fact."""
    return {
        "type": "json_schema",
        "schema": {
            "type": "object",
            "properties": {
                "place_type": {
                    "type": "string",
                    "enum": [pt.slug for pt in catalog.PLACE_TYPES],
                    "description": "What this place literally is. Exactly one.",
                },
                "themes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "slug": {
                                "type": "string",
                                "enum": [t.slug for t in catalog.THEMES],
                            },
                            "strength": {
                                "type": "string",
                                "enum": list(STRENGTH_RELEVANCE),
                                "description": (
                                    "'defining' = a main reason this place matters; "
                                    "'strong' = clearly true and significant; "
                                    "'related' = true but secondary."
                                ),
                            },
                            "reason": {
                                "type": "string",
                                "description": (
                                    "One short clause saying why this theme applies to "
                                    "this specific place."
                                ),
                            },
                        },
                        "required": ["slug", "strength", "reason"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["place_type", "themes"],
            "additionalProperties": False,
        },
    }


def _get_client() -> anthropic.Anthropic:
    if not settings.anthropic_api_key:
        raise CategoryClassificationError(
            "Category classification service is not configured on the server."
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
                raise CategoryClassificationError(
                    "Category classification did not return valid structured output."
                ) from exc
            if isinstance(parsed, dict):
                return parsed
    raise CategoryClassificationError(
        "Category classification did not return structured output."
    )


def classify_with_model(
    *,
    name: str,
    locality: str | None = None,
    formatted_address: str | None = None,
    google_primary_type: str | None = None,
    google_types: list[str] | None = None,
    description: str | None = None,
    place_kind: str | None = None,
) -> list[category_rules.ProposedCategory]:
    """Ask the model to classify one already-identified place.

    Returns proposals in the same shape the deterministic rules produce, so
    category_assignment treats both identically. Raises
    CategoryClassificationError on any failure; never fabricates a result.
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
                        name=name,
                        locality=locality,
                        formatted_address=formatted_address,
                        google_primary_type=google_primary_type,
                        google_types=google_types,
                        description=description,
                        place_kind=place_kind,
                    ),
                }
            ],
            output_config={"format": _output_schema()},
        )
    except anthropic.APIStatusError as exc:
        logger.warning("Anthropic API error (category classification): status=%s", exc.status_code)
        raise CategoryClassificationError(
            f"Category classification request failed (status {exc.status_code})."
        ) from exc
    except Exception as exc:
        logger.warning("Anthropic request failed (category classification): %s", type(exc).__name__)
        raise CategoryClassificationError(
            "Could not reach the category classification service."
        ) from exc

    return validate_model_output(_extract_json(response))


def validate_model_output(raw: dict) -> list[category_rules.ProposedCategory]:
    """Turn raw model output into proposals, dropping anything invalid.

    A second belt behind the schema enums: enforces the catalog membership
    again, drops unknown strengths, de-duplicates, and applies MAX_AI_THEMES.
    Pure and side-effect free, so it is directly testable without a model
    call.
    """
    place_type_slug = raw.get("place_type")
    if not isinstance(place_type_slug, str) or not catalog.exists(
        catalog.KIND_PLACE_TYPE, place_type_slug
    ):
        place_type_slug = catalog.OTHER_PLACE_TYPE

    proposals = [
        category_rules.ProposedCategory(
            kind=catalog.KIND_PLACE_TYPE,
            slug=place_type_slug,
            relevance=100,
            confidence=AI_CONFIDENCE,
            is_primary=True,
            source="ai",
            rationale="classified by model",
        )
    ]

    seen: set[str] = set()
    scored: list[tuple[int, str, str]] = []
    for item in raw.get("themes") or []:
        if not isinstance(item, dict):
            continue
        slug = item.get("slug")
        strength = item.get("strength")
        if not isinstance(slug, str) or slug in seen:
            continue
        if not catalog.exists(catalog.KIND_THEME, slug):
            continue
        if slug in (catalog.OTHER_THEME,):
            continue
        relevance = STRENGTH_RELEVANCE.get(strength if isinstance(strength, str) else "")
        if relevance is None:
            continue
        reason = item.get("reason")
        seen.add(slug)
        scored.append((relevance, slug, reason if isinstance(reason, str) else ""))

    scored.sort(key=lambda row: row[0], reverse=True)
    for index, (relevance, slug, reason) in enumerate(scored[:MAX_AI_THEMES]):
        proposals.append(
            category_rules.ProposedCategory(
                kind=catalog.KIND_THEME,
                slug=slug,
                relevance=relevance,
                confidence=AI_CONFIDENCE,
                is_primary=(index == 0),
                source="ai",
                rationale=reason.strip()[:200] or "classified by model",
            )
        )
    return proposals
