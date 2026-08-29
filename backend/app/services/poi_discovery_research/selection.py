"""Chooses which OSM candidates are worth anchoring a place experience to.

THE MODEL'S JOB HERE IS DELIBERATELY NARROW. It receives a fixed, numbered list
of places that OpenStreetMap says genuinely exist, and returns the INDICES of
the ones worth keeping, plus a one-line reason for each. It never supplies a
name, never supplies a coordinate, and never adds an entry -- an index outside
the list is discarded rather than interpreted.

That shape is what makes fabrication structurally impossible rather than merely
discouraged. Every stored Location's identity and position come from OSM; only
the judgement of "is this worth asking a guide about?" comes from the model,
and a wrong judgement costs one mediocre card, not a fictional landmark.

Judgement is genuinely needed: OSM near a city centre returns Pizza Hut and a
chain coffee shop alongside a 300-year-old temple and a named viewpoint. All
are real; only some are worth a "you're here" invitation.
"""

import json
import logging

import anthropic

from app.core.config import settings
from app.services.poi_discovery_research.osm_provider import OsmPlace

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are choosing which real places are worth asking a travel \
guide to report on, from a list of places that definitely exist.

Every place in the list is real and its location is already known. You are NOT \
verifying them and NOT locating them. You are only deciding which ones a \
traveller standing nearby would find genuinely interesting or useful to hear \
about from someone who is there right now.

KEEP a place when it is:
  - locally distinctive: a named temple, bridge, viewpoint, park, market, \
monument, historic site, or natural feature
  - an independent or locally-known cafe, restaurant, bakery or tea stall that \
gives a place its character
  - somewhere a traveller would plausibly stop, look at, photograph, or ask about
  - a landmark useful for orientation

DROP a place when it is:
  - a chain or franchise with no local character (international fast food, \
global coffee chains, chain hotels)
  - generic infrastructure a traveller would never remark on
  - so ordinary that a report about it would tell a future traveller nothing
  - essentially a duplicate of another entry you are already keeping

Keep FEWER, better places. An empty selection is a valid answer if nothing in \
the list is interesting. Do not keep something just to fill the list.

For each place you keep, give a short factual reason describing what it is.

THE REASON MUST NOT GUESS. You know only two things about each place: its name \
and its kind. Anything else -- what it serves, how old it is, who runs it, what \
it is known for, what cuisine it offers -- you do NOT know, and inferring it \
from the name is guessing, not describing.

  BAD:  "Likely serving South Indian cuisine given the name"
  BAD:  "A named eatery specializing in paratha"
  BAD:  "A historic temple popular with locals"
  GOOD: "A restaurant."
  GOOD: "A Hindu temple."
  GOOD: "A named park."

Write the plainest true sentence you can. A dull accurate reason is correct; an \
interesting invented one is a defect."""

# Prompt instruction alone is not enough here -- the first run produced
# "likely serving South Indian cuisine given the name" and "specializing in
# paratha" from nothing but a restaurant's name. These reasons are stored as
# the Location's description and then feed place-question research, so a guess
# admitted here is laundered into apparent fact downstream. A reason containing
# any of these is discarded and replaced with the plain OSM kind, which is
# always true.
_SPECULATION_MARKERS = (
    "likely",
    "probably",
    "perhaps",
    "possibly",
    "suggests",
    "suggesting",
    "given the name",
    "given its name",
    "appears to",
    "seems to",
    "may be",
    "might be",
    "presumably",
    "specializing in",
    "specialising in",
    "known for",
    "popular with",
    "popular among",
    "famous for",
)


def _clean_reason(reason: str, place: OsmPlace) -> str:
    """A reason we can stand behind, or the plain OSM kind instead.

    Falling back is cheap and honest: "A restaurant." is always true, and the
    downstream card reads no worse for it.
    """
    text = (reason or "").strip()[:500]
    if not text:
        return ""
    lowered = text.lower()
    for marker in _SPECULATION_MARKERS:
        if marker in lowered:
            logger.info(
                "Dropped speculative reason for %r (contained %r).", place.name, marker
            )
            return f"A {place.place_kind}."
    return text

OUTPUT_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "selected": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {
                            "type": "integer",
                            "description": "The number of a place from the given list. Never a new place.",
                        },
                        "reason": {
                            "type": "string",
                            "description": (
                                "One short, plain, literally-true line about what this place is, "
                                "using only its name and kind. Never guess cuisine, age, "
                                "speciality, ownership or reputation from the name."
                            ),
                        },
                    },
                    "required": ["index", "reason"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["selected"],
        "additionalProperties": False,
    },
}


def _build_user_message(places: list[OsmPlace]) -> str:
    lines = ["Places that exist near this location:", ""]
    for i, place in enumerate(places):
        lines.append(f"{i}. {place.name} — {place.place_kind}")
    lines.append("")
    lines.append("Return the indices of the ones worth asking a guide to report on.")
    return "\n".join(lines)


def select_places(places: list[OsmPlace], limit: int) -> list[tuple[OsmPlace, str]]:
    """Returns (place, reason) for the chosen candidates, best-effort.

    NEVER RAISES. Selection is a quality filter, not a correctness requirement:
    if the model is unavailable or misbehaves, falling back to the OSM list
    unfiltered is far better than discovering nothing. Every candidate is real
    either way -- the only thing lost is the chain-shop filtering.
    """
    if not places:
        return []

    def _fallback() -> list[tuple[OsmPlace, str]]:
        return [(p, "") for p in places[:limit]]

    if not settings.anthropic_api_key:
        logger.info("No Anthropic key configured -- keeping OSM places unfiltered.")
        return _fallback()

    try:
        client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key,
            # No web search here, so this is an ordinary single-turn request
            # and uses the normal (short) timeout rather than the research one.
            timeout=settings.anthropic_request_timeout_seconds,
        )
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_output_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_user_message(places)}],
            output_config={"format": OUTPUT_SCHEMA},
        )
        raw = None
        for block in response.content:
            if getattr(block, "type", None) == "text" and block.text.strip():
                raw = json.loads(block.text)
                break
        if not isinstance(raw, dict):
            raise ValueError("no structured output")
    except Exception as exc:  # noqa: BLE001 -- deliberate best-effort boundary
        logger.warning("Place selection failed (%s) -- keeping OSM places unfiltered.", type(exc).__name__)
        return _fallback()

    chosen: list[tuple[OsmPlace, str]] = []
    seen: set[int] = set()
    for item in raw.get("selected") or []:
        if not isinstance(item, dict):
            continue
        index = item.get("index")
        # An index outside the supplied list is discarded, never interpreted --
        # this is the guard that stops the model introducing anything that
        # wasn't in the real OSM candidate set.
        if not isinstance(index, int) or index < 0 or index >= len(places) or index in seen:
            continue
        seen.add(index)
        place = places[index]
        chosen.append((place, _clean_reason(item.get("reason") or "", place)))
        if len(chosen) >= limit:
            break

    logger.info("Selected %d of %d OSM place(s).", len(chosen), len(places))
    return chosen
