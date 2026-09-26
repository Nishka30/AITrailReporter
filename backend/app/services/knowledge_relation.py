"""CONFIRMS / CONTRADICTS / UNCERTAIN -- Part 2 of the knowledge-architecture
hardening pass.

WHAT THIS DECIDES, AND WHO OWNS THE OUTCOME
When a re-verification question about an ALREADY-VERIFIED CategoryKnowledge
item gets a new, moderation-approved answer, something has to decide whether
that answer reconfirms the standing fact, overturns it, or is too ambiguous
to tell. This module is that judgement -- and ONLY the judgement. It never
touches CategoryKnowledge, never creates a row, never sets last_verified_at.
The caller (app/services/observation_moderation.py::_maybe_verify_category_knowledge)
owns every state transition; this module just returns a RelationResult.

WHY NOT A NAIVE STRING COMPARISON
"if answer_text != old_knowledge_text: contradiction" would flag every
rephrasing of the same fact as a contradiction -- guides don't repeat
knowledge_text verbatim. So the fast path here checks SIMILARITY (token
overlap) and a small set of plain-language affirmative openers ("yes",
"still true", ...), not exact equality.

WHY AN LLM FOR THE REST, AND WHY IT IS ISOLATED HERE
Genuine contradiction detection -- "the guide's answer describes a state of
affairs incompatible with the existing fact, and here is the corrected fact"
-- is a semantic judgement free text does not yield to deterministic rules.
This is the ONE place in this system an LLM is asked to make that judgement,
and its output is treated as untrusted: the enum is validated, a CONTRADICTS
verdict with no usable replacement text is downgraded to UNCERTAIN rather
than trusted at face value, and ANY provider failure also becomes UNCERTAIN.
classify_relation() therefore never raises and never guesses -- see Part 2E
of the hardening directive: "do NOT silently choose one interpretation."
"""

import json
import logging
import re
from dataclasses import dataclass

import anthropic

from app.core.config import settings

logger = logging.getLogger(__name__)

RELATION_CONFIRMS = "confirms"
RELATION_CONTRADICTS = "contradicts"
RELATION_UNCERTAIN = "uncertain"

# Deterministic fast path, checked BEFORE ever spending an LLM call. Deliberately
# conservative: it only ever returns CONFIRMS (the safe direction to guess
# cheaply), never CONTRADICTS -- a false contradiction would destroy trust in
# standing knowledge, whereas a missed cheap-confirm just costs one LLM call.
_CONFIRM_SIMILARITY_THRESHOLD = 0.5
_AFFIRMATIVE_MARKERS = (
    "no change", "no changes", "nothing has changed", "nothing changed",
    "still true", "still the case", "still like this", "still is",
    "still same", "same as before", "same as always",
    "yes", "yeah", "yep", "correct", "confirmed", "unchanged",
    "that's right", "that is right", "that's correct",
)
_STOPWORDS = frozenset(
    {"a", "an", "the", "is", "are", "it", "to", "of", "and", "this", "that", "still", "was", "were"}
)


def _tokens(text: str) -> set[str]:
    words = re.sub(r"[^a-z0-9\s]", " ", text.lower()).split()
    return {w for w in words if w and w not in _STOPWORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class KnowledgeRelationProviderError(Exception):
    """Any failure that prevents an LLM classification. Always caught inside
    classify_relation -- callers never see this; a failure here becomes
    UNCERTAIN, never a raised exception (moderation approval must never be
    blocked by this judgement failing)."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


@dataclass
class RelationResult:
    relation: str
    # Only meaningful when relation == RELATION_CONTRADICTS: the short,
    # factual replacement text, derived ONLY from what the new answer said --
    # never invented, never padded (see supersede_knowledge_item, the only
    # place this ever gets written to a row).
    new_knowledge_text: str | None = None


def _classify_deterministic(old_text: str, new_text: str) -> RelationResult | None:
    """Returns a RelationResult only when confidently CONFIRMS; None means
    "the fast path can't tell, ask the LLM" -- never a signal to contradict."""
    lowered = new_text.strip().lower()
    if any(lowered.startswith(marker) for marker in _AFFIRMATIVE_MARKERS):
        return RelationResult(RELATION_CONFIRMS)
    if _jaccard(_tokens(old_text), _tokens(new_text)) >= _CONFIRM_SIMILARITY_THRESHOLD:
        return RelationResult(RELATION_CONFIRMS)
    return None


_RELATION_SYSTEM_PROMPT = """You judge whether a guide's new answer, submitted to \
RE-VERIFY one specific, already-trusted piece of knowledge about a place, \
CONFIRMS it, CONTRADICTS it, or is too ambiguous to tell (UNCERTAIN).

CONFIRMS -- the new answer says the existing knowledge is still true, even if \
worded completely differently from the original.

CONTRADICTS -- the new answer clearly states something that cannot both be \
true alongside the existing knowledge (a changed closing time, a service that \
no longer exists, a fact that has reversed). When you decide CONTRADICTS, also \
write new_knowledge_text: a short, factual restatement of what is now true, \
based ONLY on what the new answer actually says -- never invented, never \
padded with anything the answer did not state.

UNCERTAIN -- anything else: off-topic, too vague, does not actually address \
the existing knowledge, or you are not genuinely confident either way. \
UNCERTAIN is a correct and expected answer, not a failure -- never guess \
CONFIRMS or CONTRADICTS when you are not sure."""


def _build_relation_user_message(
    old_text: str, new_text: str, category_display_name: str, place_name: str
) -> str:
    return (
        f"Place: {place_name}\n"
        f"Category: {category_display_name}\n\n"
        f"EXISTING KNOWLEDGE (already verified):\n{old_text}\n\n"
        f"NEW GUIDE ANSWER (re-verification):\n{new_text}\n"
    )


_RELATION_OUTPUT_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "relation": {
                "type": "string",
                "enum": [RELATION_CONFIRMS, RELATION_CONTRADICTS, RELATION_UNCERTAIN],
            },
            "new_knowledge_text": {"type": ["string", "null"]},
        },
        "required": ["relation", "new_knowledge_text"],
        "additionalProperties": False,
    },
}


def _classify_with_llm(
    old_text: str, new_text: str, category_display_name: str, place_name: str
) -> RelationResult:
    if not settings.anthropic_api_key:
        raise KnowledgeRelationProviderError(
            "Knowledge relation classification is not configured on the server."
        )
    client = anthropic.Anthropic(
        api_key=settings.anthropic_api_key,
        timeout=settings.anthropic_request_timeout_seconds,
    )
    try:
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=300,
            system=_RELATION_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": _build_relation_user_message(
                        old_text, new_text, category_display_name, place_name
                    ),
                }
            ],
            output_config={"format": _RELATION_OUTPUT_SCHEMA},
        )
    except Exception as exc:
        logger.warning("Knowledge relation classification failed: %s", type(exc).__name__)
        raise KnowledgeRelationProviderError(
            "Could not classify the relationship between this evidence and existing knowledge."
        ) from exc

    parsed = None
    for block in response.content:
        if getattr(block, "type", None) == "text" and block.text.strip():
            try:
                parsed = json.loads(block.text.strip())
            except json.JSONDecodeError:
                parsed = None
            break

    if not isinstance(parsed, dict) or parsed.get("relation") not in (
        RELATION_CONFIRMS, RELATION_CONTRADICTS, RELATION_UNCERTAIN,
    ):
        raise KnowledgeRelationProviderError(
            "Knowledge relation classification returned an unexpected result."
        )

    relation = parsed["relation"]
    if relation == RELATION_CONTRADICTS:
        new_text_out = parsed.get("new_knowledge_text")
        if not isinstance(new_text_out, str) or len(new_text_out.strip()) < 5:
            # A contradiction with no usable replacement fact must never
            # become a guessed one -- treat as UNCERTAIN instead (Part 2A/2E).
            return RelationResult(RELATION_UNCERTAIN)
        return RelationResult(RELATION_CONTRADICTS, new_knowledge_text=new_text_out.strip())
    return RelationResult(relation)


def classify_relation(
    old_knowledge_text: str,
    new_answer_text: str,
    category_display_name: str,
    place_name: str,
) -> RelationResult:
    """Backend-owned entry point. Never raises, never returns an unvalidated
    relation: a provider failure or an ambiguous/malformed LLM response both
    become UNCERTAIN, exactly like the case where the model itself judged
    the evidence too ambiguous to call."""
    fast = _classify_deterministic(old_knowledge_text, new_answer_text)
    if fast is not None:
        return fast
    try:
        return _classify_with_llm(old_knowledge_text, new_answer_text, category_display_name, place_name)
    except KnowledgeRelationProviderError:
        return RelationResult(RELATION_UNCERTAIN)
