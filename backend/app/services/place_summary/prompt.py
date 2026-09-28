"""Prompt and output schema for turning research findings into a reusable,
structured place summary -- for the future Travelers website, not for a guide
standing at the place (that is place_question_research/prompt.py's job).

Kept separate from the provider, same reasoning as every other prompt module
in this codebase: the prompt is what gets tuned, and isolating it keeps that
from touching SDK code.

SECURITY: the findings embedded in the user message are UNTRUSTED WEB TEXT,
scrubbed at the provider edge (research/sanitize.py) before they ever reach
here. Same delimiter/notice convention as place_question_research/prompt.py.
"""

from app.services.research import sanitize

SYSTEM_PROMPT = f"""You write a short, structured, FACTUAL summary of a real \
place, for a travel website reader who has never been there and may be \
deciding whether to visit.

You are given: the name of a real place, where it is, and research about \
that place gathered from the web with citations. You do NOT search. Your job \
is to organize what the research actually says into a small number of \
clearly-labelled fields.

{sanitize.UNTRUSTED_DATA_NOTICE}

RULES YOU MUST FOLLOW EXACTLY

- Use ONLY the research you were given. Not general knowledge about the \
region, not what seems plausible for a place of this type, and not anything \
you know about somewhere with a similar name. If the research says nothing \
useful for a field, leave that field null/empty -- an honest gap beats a \
plausible-sounding invention.
- NEVER INVENT a business, landmark, fact, statistic, opening time, price, \
or historical claim that is not in the research.
- Attribute rather than assert where sources disagree or where a claim is not \
independently verified -- write "sources describe..." / "known for..." \
rather than stating a contested detail as flatly certain.
- This summary is read BEFORE any local contributions exist for the place, so \
write it as general orientation for a traveler, not as an answer to a \
specific question.
- description: 2-4 sentences, what the place fundamentally IS.
- known_for: one short phrase or sentence naming what the place is most \
recognized for, or null if the research doesn't establish one.
- highlights: specific noteworthy features/attractions the research actually \
names (not a generic list of "beautiful views" unless the research says so \
specifically). Empty list if none.
- things_to_do: concrete activities the research says are possible here. \
Empty list if the research doesn't cover this.
- important_facts: specific, checkable facts the research states (history, \
scale, significance). Never a restatement of description. Empty list if none.
- practical_info: logistics a traveler would want (getting there, timing, \
access) ONLY if the research actually states them -- null otherwise. Never \
invent a price, hour, or distance not in the research.
- warnings: safety, access, or seasonal cautions the research actually \
mentions. Empty list if none -- do not invent a generic caution.
- Every field must be traceable to the research given. If you cannot support \
a field from the research, leave it null/empty rather than writing something \
generic that would be true of any similar place.
- source_urls: every URL from the research that materially supports content \
you wrote, copied EXACTLY. Never invented, shortened, or reconstructed.
- If the research contains nothing usable at all, set found_information=false \
and leave every content field null/empty -- that is a correct and expected \
outcome for a little-documented place, not a failure."""


def build_user_message(
    place_name: str,
    latitude: float,
    longitude: float,
    description: str | None,
    locality: str | None,
    findings: list,
    category: str | None = None,
    subcategory: str | None = None,
) -> str:
    lines = [
        "THE PLACE",
        f"Name: {place_name}",
        f"Coordinates: {latitude:.5f}, {longitude:.5f}",
    ]
    if locality:
        lines.append(f"Locality: {locality}")
    if category:
        category_line = f"Category: {category} / {subcategory}" if subcategory else f"Category: {category}"
        lines.append(category_line)
    if description:
        lines.append(f"Known description: {description}")

    lines.append("")
    lines.append("RESEARCH ABOUT THIS PLACE")
    for finding in findings:
        lines.append("")
        lines.append(f"--- finding topic: {finding.topic} ---")
        lines.append("Sources you may cite for this finding:")
        for source in finding.sources:
            title = f" — {source.title}" if source.title else ""
            lines.append(f"  {source.url}{title}")
        lines.append(sanitize.as_untrusted_block(finding.summary))

    lines.append("")
    lines.append(
        f"Using ONLY the research above, write a structured summary of {place_name} "
        "for a traveler who has never been there."
    )
    return "\n".join(lines)


OUTPUT_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "found_information": {
                "type": "boolean",
                "description": (
                    "True only if the research contained something usable about this "
                    "exact place. False means every content field below must be "
                    "null/empty."
                ),
            },
            "description": {
                "type": ["string", "null"],
                "description": "2-4 sentences on what the place fundamentally is.",
            },
            "known_for": {
                "type": ["string", "null"],
                "description": "What the place is most recognized for, or null.",
            },
            "highlights": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific noteworthy features/attractions the research names.",
            },
            "things_to_do": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Concrete activities the research says are possible here.",
            },
            "important_facts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific, checkable facts (history, scale, significance).",
            },
            "practical_info": {
                "type": ["string", "null"],
                "description": "Logistics (getting there, timing, access) only if stated.",
            },
            "warnings": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Safety/access/seasonal cautions the research actually mentions.",
            },
            "source_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Every URL that materially supports the content, copied exactly.",
            },
        },
        "required": [
            "found_information",
            "description",
            "known_for",
            "highlights",
            "things_to_do",
            "important_facts",
            "practical_info",
            "warnings",
            "source_urls",
        ],
        "additionalProperties": False,
    },
}
