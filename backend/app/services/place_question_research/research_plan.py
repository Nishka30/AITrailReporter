"""How a place gets researched: which queries to run, in what order, and when
to stop.

WHY A PLAN AND NOT ONE QUERY
"Things to do in Bengaluru" is the failure this whole feature exists to escape.
Research has to be progressively specific -- anchored to a place this system
already knows exists by name, in a named locality -- or it returns city-level
tourism copy that produces exactly the generic prompts we are trying to kill.

WHY TWO QUERIES AND NOT SIX
Each query is a paid web search. The second one runs ONLY if the first actually
found something, so a place nobody has written about costs one request rather
than a fixed budget. That gate is deterministic -- a length-and-sources check in
code, no model call -- because the cheapest way to control spend is to not make
the call at all.

The two queries do genuinely different work:

  interest -- what is distinctive about this exact place, and what do visitors
              specifically notice? This is where the material for a good
              invitation comes from ("the idol wears diamond armour on festival
              days", "people come for the view of the ridge").
  current  -- what varies, what is disputed between sources, what changed
              recently? This is where the material for a VERIFIABLE invitation
              comes from: if two listings disagree about opening time, the
              person standing at the door can settle it, and that is precisely
              the field intelligence this product wants.

The `current` query is scoped to the entity, never to the surrounding city. An
area-scoped version of it was tried and returned civic news and unrelated
press releases -- true, sourced, and worthless for asking someone what is in
front of them.
"""

import logging

from app.core.config import settings
from app.services.research.base import ResearchFinding, ResearchProviderError

logger = logging.getLogger(__name__)

TOPIC_INTEREST = "interest"
TOPIC_CURRENT = "current"


def describe_place(
    place_name: str,
    place_kind: str | None,
    locality: str | None,
) -> str:
    """The most identifying phrase available for this place.

    The locality is what makes web research work at all: "Ganesh Temple" is
    hopeless on its own and resolves correctly as "Ganesh Temple, Koramangala,
    Bengaluru". When locality is unknown the name still goes out alone rather
    than being padded with a guess about where it is.
    """
    parts = [place_name]
    if place_kind:
        parts.append(f"({place_kind})")
    if locality:
        parts.append(f"in {locality}")
    return " ".join(parts)


def build_interest_query(descriptor: str) -> str:
    return (
        f"{descriptor}: what do visitors specifically notice, mention or "
        "photograph about this exact place? Include distinctive physical "
        "features, anything unusual about how it looks, local names or "
        "nicknames, what people come here for, food or items associated with "
        "it, and any local story or custom tied to this specific spot. Report "
        "only what sources actually say about this place, not about the "
        "surrounding city or about places of this type in general. If sources "
        "say little about this specific place, say so."
    )


def build_current_query(descriptor: str) -> str:
    return (
        f"{descriptor}: what is currently true about visiting this exact "
        "place? Opening hours or timings (note if sources disagree), access, "
        "current condition, crowding, entry rules, and any recent change, "
        "renovation or closure. Report only what sources say about this "
        "specific place."
    )


def run_research_plan(
    provider,
    place_name: str,
    place_kind: str | None,
    locality: str | None,
) -> list[ResearchFinding]:
    """Runs the plan and returns whatever was genuinely found.

    Returns an empty list when the web has nothing specific to say about this
    place. That is a correct and common outcome -- most of the world is not
    written about -- and it must stay honest, because "no findings" is what
    stops the generation step from being asked to invent something.

    Never raises for a provider failure on the SECOND query: one usable finding
    is still worth generating from, and losing it to a transient error would be
    a worse outcome than a slightly thinner research set.
    """
    descriptor = describe_place(place_name, place_kind, locality)
    findings: list[ResearchFinding] = []

    try:
        interest = provider.run_query(
            build_interest_query(descriptor), topic=TOPIC_INTEREST
        )
    except ResearchProviderError:
        # The first query failing means we have nothing at all -- surfaced to
        # the caller so the run is recorded as failed rather than as "this
        # place is uninteresting", which would suppress retries for weeks.
        raise

    if interest.is_usable:
        findings.append(interest)
    else:
        # Deterministic gate: no second paid search for a place the web does
        # not cover. No model call is needed to know this.
        logger.info("No usable research for %r -- skipping follow-up query.", place_name)
        return findings

    if settings.perplexity_max_queries_per_place < 2:
        return findings

    try:
        current = provider.run_query(
            build_current_query(descriptor),
            topic=TOPIC_CURRENT,
            # Not restricted by recency: opening hours and access details are
            # mostly published on undated pages, and a recency filter here
            # discarded them in favour of dated local news that had nothing to
            # do with the place.
        )
        if current.is_usable:
            findings.append(current)
    except ResearchProviderError as exc:
        logger.warning(
            "Follow-up research failed for %r (%s) -- continuing with %d finding(s).",
            place_name,
            exc.message,
            len(findings),
        )

    return findings
