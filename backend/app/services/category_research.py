"""Grounding a category-gap question in real research -- Part 1 of the
knowledge-architecture hardening pass.

THE ORDER THIS ENFORCES, for one (Location, missing-category) gap:
  1. Reuse an EXISTING finding (the whole-location interest/current research
     already run by place_questions.ensure_researched) if it happens to say
     something about this category -- zero additional spend.
  2. Otherwise reuse a previous TARGETED finding for this exact category, if
     one was ever run -- also zero additional spend, and this is a permanent
     de-dup: see get_or_create_category_finding's docstring for why a
     targeted query for the same (Location, category) is never repeated
     inside one refresh window.
  3. Otherwise, and only otherwise, run exactly ONE new targeted Perplexity
     query scoped to this Location + this category.

TWO INDEPENDENT CLOCKS, KEPT INDEPENDENT (see place_questions.py's own
module docstring and guides.py's popular-questions route): this module is
never gated on place_question_refresh_days / is_research_stale -- a category
gap can trigger a targeted query at any time regardless of whether the
whole-location Perplexity research happens to be stale. The refresh window
is reused here ONLY as a "don't retry a previously-unusable targeted query
every single generation call" cooldown (see get_or_create_category_finding),
not as a gate on whether to run at all.

SAFETY BOUNDARY THIS ENFORCES STRUCTURALLY: a PlaceResearchFinding produced
or reused here is only ever used to GROUND A QUESTION (see
place_question_research/anthropic_provider.py::generate_category_question).
Nothing in this module -- or anywhere reachable from it -- ever creates or
mutates a CategoryKnowledge row. Only a moderated, guide-answered Observation
does that (see extractions.py / observation_moderation.py). Perplexity
research is evidence for what's worth ASKING, never evidence of what's true.
"""

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.location import Location
from app.db.models.place_research_finding import PlaceResearchFinding
from app.services.place_question_research import research_plan
from app.services.research import perplexity_provider
from app.services.research.base import ResearchProviderError

logger = logging.getLogger(__name__)

# Marks a finding as having come from a category-TARGETED query rather than
# the whole-location interest/current research plan (see
# place_question_research/research_plan.py's PLACE_RESEARCH_TOPICS) -- so a
# targeted finding can always be found again by (location, category) without
# re-querying, and so it is never confused with the whole-location topics.
CATEGORY_FINDING_TOPIC_PREFIX = "category:"

# A finding needs at least this much specific, on-topic text to be worth
# grounding a question in -- mirrors ResearchFinding.is_usable's own floor
# (40 chars), applied here to the persisted DB row instead of the live
# dataclass.
_MIN_USABLE_SUMMARY_CHARS = 40


def _category_topic(category_slug: str) -> str:
    return f"{CATEGORY_FINDING_TOPIC_PREFIX}{category_slug}"


def _category_keywords(category_slug: str, category_display_name: str) -> list[str]:
    """Cheap, deterministic relevance signal -- no LLM/embedding call spent
    just to decide whether an existing finding is on-topic. Words length <= 2
    are dropped (e.g. "of", "at") as too weak to mean anything on their own."""
    words = set(category_slug.replace("_", " ").split()) | set(category_display_name.lower().split())
    return [w for w in words if len(w) > 2]


def _row_is_usable(row: PlaceResearchFinding) -> bool:
    return bool(row.source_urls) and len((row.summary or "").strip()) >= _MIN_USABLE_SUMMARY_CHARS


def find_relevant_finding(
    db: Session, location_id: UUID, category_slug: str, category_display_name: str
) -> PlaceResearchFinding | None:
    """The best EXISTING finding for this Location (any topic, including a
    prior category-targeted one) that actually says something about this
    category, or None. Purely a keyword-overlap score against persisted
    text -- deterministic and free, never a paid call."""
    keywords = _category_keywords(category_slug, category_display_name)
    if not keywords:
        return None

    findings = list(
        db.execute(
            select(PlaceResearchFinding)
            .where(PlaceResearchFinding.location_id == location_id)
            .order_by(PlaceResearchFinding.retrieved_at.desc())
        ).scalars()
    )

    best: PlaceResearchFinding | None = None
    best_score = 0
    for finding in findings:
        if not _row_is_usable(finding):
            continue
        text = finding.summary.lower()
        score = sum(1 for kw in keywords if kw in text)
        if score > best_score:
            best_score = score
            best = finding
    return best if best_score >= 1 else None


def get_existing_targeted_finding(
    db: Session, location_id: UUID, category_slug: str
) -> PlaceResearchFinding | None:
    stmt = (
        select(PlaceResearchFinding)
        .where(
            PlaceResearchFinding.location_id == location_id,
            PlaceResearchFinding.topic == _category_topic(category_slug),
        )
        .order_by(PlaceResearchFinding.retrieved_at.desc())
    )
    return db.execute(stmt).scalars().first()


def perform_targeted_category_research(
    db: Session, claim: PlaceResearchFinding, query: str, topic: str
) -> PlaceResearchFinding | None:
    """Runs the ONE Perplexity call for an already-claimed (location, topic)
    slot (see get_or_create_category_finding) and fills in the claim row that
    was committed, lock-free, just before this runs -- slow external work
    must never hold a database row lock (same shape as
    place_questions.ensure_researched's claim-then-release). Returns None
    only when the call itself failed (Perplexity unavailable/erroring), which
    is the caller's signal to fall back to the deterministic template
    (Part 1E). On failure the claim row is DELETED rather than left as a
    cooldown placeholder -- a transient provider outage must not block every
    later request for this (location, category) for a full
    place_question_refresh_days window; that cooldown is only earned by a
    successful call that came back too thin to use (see
    get_or_create_category_finding's "too recent to retry" branch)."""
    try:
        provider = perplexity_provider.get_provider()
        result = provider.run_query(query, topic=topic)
    except ResearchProviderError as exc:
        logger.info(
            "Targeted category research unavailable for location %s / %s: %s",
            claim.location_id, topic, exc.message,
        )
        db.delete(claim)
        db.commit()
        return None

    claim.provider = result.provider
    claim.model = result.model
    claim.summary = result.summary
    claim.source_urls = result.source_urls or None
    claim.source_titles = result.source_titles or None
    claim.retrieved_at = result.retrieved_at
    claim.input_tokens = result.input_tokens
    claim.output_tokens = result.output_tokens
    claim.cost_usd = result.cost_usd
    db.add(claim)
    db.flush()
    return claim


def get_or_create_category_finding(
    db: Session,
    location: Location,
    category_slug: str,
    category_display_name: str,
    *,
    now: datetime | None = None,
) -> PlaceResearchFinding | None:
    """The single entry point generation should call for one missing-category
    gap. Returns a USABLE finding to ground a question in, or None (meaning:
    use the deterministic template -- Part 1E's designed fallback, not an
    error state).

    COST PROTECTION: a targeted query for this exact (location, category) is
    performed AT MOST ONCE per settings.place_question_refresh_days -- the
    same window the whole-location research plan already uses, reused here
    only as a "don't hammer a place with nothing to say" cooldown, never as a
    gate on whether category questions may be generated at all (see the
    module docstring's "two independent clocks" note).

    CONCURRENCY: the "does anything usable already exist" check and the
    decision to spend on a new targeted query both happen under a
    SELECT ... FOR UPDATE lock on this Location row, released (via commit)
    BEFORE the Perplexity call itself -- the same claim-then-release shape
    place_questions.ensure_researched uses for whole-location research.
    Without this, two callers landing on the same (location, category) gap in
    the same window (now plausible since category generation runs as a
    background task -- see guides.py's popular-questions route) could both
    read "nothing exists yet" and both pay for a Perplexity call, producing
    two rows for what the module docstring promises is never repeated.
    """
    now = now or datetime.now(timezone.utc)

    # Claim: lock this Location so a concurrent caller for the same
    # (location, category) is serialized behind whatever this call commits,
    # instead of racing it on the same read.
    db.execute(select(Location.id).where(Location.id == location.id).with_for_update())

    relevant = find_relevant_finding(db, location.id, category_slug, category_display_name)
    if relevant is not None:
        db.commit()
        return relevant

    existing_targeted = get_existing_targeted_finding(db, location.id, category_slug)
    if existing_targeted is not None:
        if _row_is_usable(existing_targeted):
            db.commit()
            return existing_targeted
        age = now - existing_targeted.retrieved_at
        if age < timedelta(days=settings.place_question_refresh_days):
            # A prior (or concurrently in-flight) targeted attempt found
            # nothing useful yet, and it hasn't been long enough to justify
            # spending on this exact (location, category) again -- the
            # deterministic template applies for now (Part 1F: no repeat
            # spend without a reason).
            db.commit()
            return None

    # Still nothing usable -- claim the slot with a placeholder row BEFORE
    # releasing the lock, so a concurrent caller's get_existing_targeted_finding
    # check above finds THIS row (an "unusable, too recent to retry" claim)
    # and backs off instead of also spending.
    topic = _category_topic(category_slug)
    descriptor = research_plan.describe_place(location.name, location.place_kind, location.locality)
    query = f"{descriptor} {category_display_name.lower()} relevance"
    claim = PlaceResearchFinding(
        location_id=location.id,
        research_id=None,
        topic=topic,
        query_text=query,
        provider="perplexity",
        summary="",
        retrieved_at=now,
    )
    db.add(claim)
    db.commit()  # releases the Location row lock
    db.refresh(claim)

    targeted = perform_targeted_category_research(db, claim, query, topic)
    if targeted is None or not _row_is_usable(targeted):
        return None
    return targeted
