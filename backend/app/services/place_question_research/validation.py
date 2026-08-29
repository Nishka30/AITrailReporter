"""Validates raw popular-question research output before anything reaches
PostgreSQL (Step 18) -- mirrors app/services/extraction/validation.py.

Deliberately more forgiving than extraction's all-or-nothing rule. Extraction
rejects a whole batch on one bad item because a partially-extracted submission
would be a misleading record of what a guide said. Here, items are independent
suggestions from a web search: dropping one malformed question and keeping five
good ones loses nothing and is strictly better for the guide than discarding
the entire research run. What is NOT tolerated is a response that isn't the
agreed shape at all -- that raises.
"""

import logging
import re

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.db.models.place_question import (
    DEFAULT_CONTRIBUTION_KIND,
    PLACE_QUESTION_CONTRIBUTION_KINDS,
)

logger = logging.getLogger(__name__)

MAX_QUESTION_LENGTH = 200
MAX_CONTEXT_NOTE_LENGTH = 160

# Openers that mark a question addressed to a READER planning a trip rather
# than to the guide standing at the place. These are exactly what the previous
# prompt produced ("Is it safe to cross if you're scared of heights?",
# "Should I use the lower or the upper bridge?") -- grammatical, researched, and
# unanswerable by someone who is simply looking at the thing.
#
# A prompt instruction alone is not enough here: this is the single failure mode
# the whole feature was corrected for, so it is also enforced in code. A dropped
# item costs one invitation; a kept one puts a useless prompt in front of a
# guide standing on a bridge.
_READER_FACING_OPENERS = (
    "should i",
    "should you",
    "do i need",
    "do you need",
    "can i",
    "will i",
    "would i",
    "how do i get",
    "how can i get",
    "what should i",
    "where should i",
    "when should i",
    "is it worth",
    "how much does",
    "how long does it take",
)

# A question about a fixed fact is not observable, however well phrased.
_FIXED_FACT_OPENERS = ("what is ", "what are ", "who is ", "who was ", "when was ", "why is ")

# Phrasings that are grammatically fine and even second-person, but are
# GENERIC IN A WAY NO GROUNDING CAN FIX -- they would read exactly the same at
# any other place, which is the specific failure mode this quality gate exists
# to catch (the "move the guide 50km away, does it still make sense?" test).
# Checked as a substring, not just a prefix: "What's this place like?" and
# "Tell us what this place is like" are both hollow regardless of where the
# sentence starts.
_TOO_GENERIC_PHRASES = (
    "what is this place like",
    "what's this place like",
    "tell us about this place",
    "tell us what this place is like",
    "what do you think of this place",
    "share your thoughts on this place",
    "what's it like here",
    "what is it like here",
    "how is the weather",
    "what's the weather like",
)


def _normalize_for_matching(text: str) -> str:
    """Lowercases and strips punctuation to a single spaced form.

    APPLIED TO BOTH SIDES OF EVERY COMPARISON, which is the point. It was
    previously applied only to the incoming question, so every phrase in the
    lists above that contained an apostrophe was DEAD: "What's this place
    like?" normalizes to "what s this place like", which never matches the
    literal "what's this place like". The most obviously generic invitation in
    the list sailed through the gate that names it.

    Normalizing the constants at import time instead of hand-writing them
    pre-normalized keeps them readable and makes the same mistake impossible to
    reintroduce.
    """
    lowered = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return " ".join(lowered.split())


_NORMALIZED_READER_FACING = tuple(_normalize_for_matching(p) for p in _READER_FACING_OPENERS)
# Trailing space preserved: these are prefix matches on whole words, so
# "what is " must not also match "what island".
_NORMALIZED_FIXED_FACT = tuple(
    _normalize_for_matching(p) + " " for p in _FIXED_FACT_OPENERS
)
_NORMALIZED_TOO_GENERIC = tuple(_normalize_for_matching(p) for p in _TOO_GENERIC_PHRASES)


class ResearchedQuestion(BaseModel):
    question_text: str = Field(min_length=8, max_length=MAX_QUESTION_LENGTH)
    contribution_kind: str = DEFAULT_CONTRIBUTION_KIND
    # REQUIRED, not optional. This is the core of the anti-hallucination /
    # anti-genericness gate: an invitation is kept only when the research step
    # can point at a SPECIFIC, traceable reason it asked. A prompt instruction
    # telling the model to ground itself is necessary but not sufficient --
    # this makes it a structural requirement no malformed or lazy item can
    # skip. "Never a generic filler note" only holds if a missing note drops
    # the invitation entirely rather than being tolerated as null.
    context_note: str = Field(min_length=8, max_length=MAX_CONTEXT_NOTE_LENGTH)
    # REQUIRED non-empty AFTER filtering to real http(s) URLs -- see
    # keep_only_http_urls below, which is what actually enforces this. Not
    # constrained here with Field(min_length=1): that would check the RAW list
    # (which could contain three non-URL strings and still "pass") before the
    # filter removes them.
    source_urls: list[str] = Field(default_factory=list)
    # Which research finding the grounding detail came from. Optional because a
    # missing label costs only traceability, not correctness -- the citation
    # allowlist below is what actually guarantees the invitation is grounded.
    finding_topic: str | None = None

    @field_validator("question_text")
    @classmethod
    def must_be_an_answerable_invitation(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned.endswith("?"):
            raise ValueError("not phrased as a question")

        lowered = _normalize_for_matching(cleaned)
        if lowered.startswith(_NORMALIZED_READER_FACING):
            raise ValueError("addressed to a reader planning a trip, not to a guide who is here")
        if lowered.startswith(_NORMALIZED_FIXED_FACT):
            raise ValueError("asks for a fixed fact rather than a present observation")
        if any(phrase in lowered for phrase in _NORMALIZED_TOO_GENERIC):
            raise ValueError("generic enough to apply to any place, not specific to this one")
        return cleaned

    @field_validator("contribution_kind")
    @classmethod
    def known_kind(cls, value: str) -> str:
        # An unrecognised kind falls back rather than rejecting the invitation:
        # the invitation itself is still useful, and 'observation' is the
        # least-presumptuous way to ask for it. A wrong kind would only mean the
        # app foregrounds the wrong control, never a wrong reward -- the rate is
        # resolved from whatever kind is actually stored.
        cleaned = (value or "").strip().lower()
        if cleaned not in PLACE_QUESTION_CONTRIBUTION_KINDS:
            logger.info("Unknown contribution_kind %r -- using %r.", value, DEFAULT_CONTRIBUTION_KIND)
            return DEFAULT_CONTRIBUTION_KIND
        return cleaned

    @field_validator("context_note")
    @classmethod
    def clean_context_note(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 8:
            # Whitespace-collapsing can shrink a technically-8-char raw value
            # below the real minimum ("   a b  " etc.) -- re-checked here so
            # the min_length on the field can't be satisfied by padding alone.
            raise ValueError("context_note is missing or too short to be a real grounding reason")
        return cleaned[:MAX_CONTEXT_NOTE_LENGTH]

    @field_validator("source_urls")
    @classmethod
    def keep_only_http_urls(cls, value: list[str]) -> list[str]:
        # Provenance must be real and inspectable -- anything that isn't an
        # http(s) URL is dropped rather than stored as a citation. What
        # survives must be non-empty: a context_note with no real source
        # behind it is exactly the "traceable research/source basis" this
        # feature is required to have, not a nice-to-have.
        cleaned = [u for u in value if isinstance(u, str) and u.startswith(("http://", "https://"))][:8]
        if not cleaned:
            raise ValueError("no real source URL -- context_note has no traceable basis")
        return cleaned


class ResearchEnvelope(BaseModel):
    """The OUTER shape only. `questions` is deliberately typed as raw dicts,
    not as list[ResearchedQuestion]: validating items here would make one
    malformed question reject the entire batch, which is exactly the
    all-or-nothing behaviour this module is documented not to want. Items are
    validated individually in validate_research_output below."""

    questions: list[dict] = Field(default_factory=list)
    found_information: bool


class ResearchValidationError(Exception):
    """The response was not the agreed shape at all (not merely a bad item)."""


def _keep_only_cited_urls(
    question: ResearchedQuestion, allowed_urls: set[str]
) -> ResearchedQuestion | None:
    """Discards citations that were not actually in the research, and the
    invitation itself if none survive.

    WHY THIS IS NECESSARY. A URL that came out of a model is a claim about
    provenance, not provenance. It can be a real-looking address for a page
    that says nothing of the kind, or a plausible reconstruction of one that
    was in the research. Either way it defeats the entire point of citing
    sources: someone auditing "why did TrailMind ask this?" would follow it and
    find nothing.

    So the citation list is intersected with the URLs that were genuinely
    retrieved for THIS place. An invitation whose grounding evaporates under
    that check is dropped rather than stored uncited -- exactly like a missing
    context_note, and for the same reason.

    An empty allowlist means no research was supplied, in which case there is
    nothing to check against and the invitation cannot be grounded at all.
    """
    if not allowed_urls:
        return None
    kept = [u for u in question.source_urls if u in allowed_urls]
    if not kept:
        logger.info(
            "Dropped an invitation citing %d URL(s) that were not in the research.",
            len(question.source_urls),
        )
        return None
    return question.model_copy(update={"source_urls": kept})


def validate_research_output(
    raw: dict, allowed_urls: set[str] | None = None
) -> list[ResearchedQuestion]:
    """Returns the valid questions, dropping individually-malformed ones.

    `allowed_urls` is every source URL actually retrieved while researching this
    place. When supplied, an invitation must cite at least one of them or it is
    dropped -- see _keep_only_cited_urls. It is optional only so the shape
    checks above stay independently testable; the real caller always passes it.

    Returns an empty list when the model reported it found nothing -- that is
    a legitimate, honest outcome ('insufficient web information'), never an
    error, and the caller records a successful research run with zero
    questions rather than retrying forever.
    """
    if not isinstance(raw, dict):
        raise ResearchValidationError("Research output was not an object.")

    try:
        envelope = ResearchEnvelope.model_validate(
            {
                "questions": raw.get("questions") or [],
                "found_information": bool(raw.get("found_information", False)),
            }
        )
    except ValidationError as exc:
        # Only reachable if `questions` isn't a list of objects at all --
        # individual bad items are filtered below, not here.
        raise ResearchValidationError(
            f"Research output had an unexpected shape: {exc.error_count()} errors"
        )

    if not envelope.found_information:
        return []

    valid: list[ResearchedQuestion] = []
    for item in envelope.questions:
        try:
            question = ResearchedQuestion.model_validate(item)
        except ValidationError:
            logger.info("Dropped one malformed researched question.")
            continue
        if allowed_urls is not None:
            grounded = _keep_only_cited_urls(question, allowed_urls)
            if grounded is None:
                continue
            question = grounded
        valid.append(question)
    return valid
