"""Place-specific invitations -- the SECOND question source.

Nothing in this module touches the knowledge-gap pipeline. It never reads
KnowledgeTypeConfig, never evaluates knowledge state, never ranks a gap, and
never creates a Question/QuestionAssignment row. These are a parallel,
secondary source that the mobile app renders BELOW the gap queue. The two
systems answer different questions:

    Questions queue -- "what does TrailMind not know yet?"   (gap-driven)
    Place questions -- "this person is standing HERE, now"   (presence-driven)

THE THREE-SOURCE CHAIN THIS ORCHESTRATES

    Google Places  ->  what physically exists here, and where
    Perplexity     ->  what the web actually says about that named thing
    Claude         ->  which of those details a person here could check

Each source is used only for what it can be trusted about. A place name and
coordinate never originate from a language model; a claim about a place never
originates from a model's memory; and the decision about what is worth asking
never originates from a search engine.

The chain is also a cost gate. Every stage can end it: no nearby place means no
research, no usable research means no generation call, and both outcomes are
recorded as honest successes rather than retried.

Concurrency follows the established pattern from extractions.py/questions.py:
the research row is claimed under SELECT ... FOR UPDATE, and the lock is
RELEASED BEFORE the external calls -- slow network work must never hold a
database row lock.
"""

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.geo import make_point
from app.db.models.curated_hub import CuratedHub
from app.db.models.location import Location
from app.db.models.place_question import PlaceQuestion, PlaceQuestionResearch
from app.db.models.place_research_finding import PlaceResearchFinding
from app.services import category_knowledge as category_knowledge_service
from app.services import category_knowledge_policy
from app.services import category_research as category_research_service
from app.services import rewards as reward_service
from app.services.place_question_research import (
    anthropic_provider,
    research_plan,
    validation,
)
from app.services.places import category_assignment
from app.services.places.google_provider import get_place_provider
from app.services.research import perplexity_provider
from app.services.research.base import ResearchFinding, ResearchProviderError

logger = logging.getLogger(__name__)

# Filler words removed when normalizing for dedup. Deliberately small: the
# goal is to collapse trivial rephrasings ("Is it safe to cross?" vs "is it
# safe to cross"), NOT to cluster semantically similar but genuinely different
# questions -- that would silently discard real questions, and this system has
# no semantic similarity capability to do it honestly.
_DEDUP_STOPWORDS = frozenset(
    {"a", "an", "the", "is", "are", "it", "to", "do", "does", "how", "what", "there", "right", "now"}
)


def normalize_question(text: str) -> str:
    """Collapses case, punctuation and filler words into the key used by the
    UNIQUE (location_id, normalized_text) constraint. Deterministic and
    dependency-free -- the DB constraint is the real guarantee, this just
    produces the key it is applied to."""
    lowered = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    words = [w for w in lowered.split() if w and w not in _DEDUP_STOPWORDS]
    return " ".join(words)


def get_research(db: Session, location_id: UUID) -> PlaceQuestionResearch | None:
    stmt = select(PlaceQuestionResearch).where(PlaceQuestionResearch.location_id == location_id)
    return db.execute(stmt).scalar_one_or_none()


def list_place_questions(db: Session, location_id: UUID) -> list[PlaceQuestion]:
    """READ ONLY -- never triggers research. The mobile app's question list
    must never block on a web search."""
    stmt = (
        select(PlaceQuestion)
        .where(PlaceQuestion.location_id == location_id, PlaceQuestion.active.is_(True))
        .order_by(PlaceQuestion.display_order, PlaceQuestion.created_at)
        .limit(settings.place_question_max_count)
    )
    return list(db.execute(stmt).scalars().all())


def get_place_question(db: Session, place_question_id: UUID) -> PlaceQuestion | None:
    return db.get(PlaceQuestion, place_question_id)


# ---------------------------------------------------------------------------
# PRIMARY (category-driven) question generation -- Location -> Categories ->
# CategoryKnowledge -> Questions. Deliberately deterministic/template-based
# rather than a new LLM call: unlike the AI-research pipeline above (which
# exists to discover what's worth asking at all), a category gap already
# fully specifies what to ask -- which category, and for a re-verification,
# the exact existing knowledge_text to re-check. Templating it costs zero
# additional Perplexity/Anthropic spend, which is the simplest way to honor
# "reuse before spending" for this half of the system. Upgrading to
# LLM-phrased questions grounded in existing place_research_findings is a
# valid follow-up (see the accompanying report), not implemented here.
# ---------------------------------------------------------------------------


def _has_open_first_ask_question(db: Session, category_assignment_id: UUID) -> bool:
    stmt = (
        select(PlaceQuestion.id)
        .where(
            PlaceQuestion.category_assignment_id == category_assignment_id,
            PlaceQuestion.verifying_knowledge_id.is_(None),
            PlaceQuestion.active.is_(True),
        )
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none() is not None


def _has_open_reverification_question(db: Session, category_knowledge_id: UUID) -> bool:
    stmt = (
        select(PlaceQuestion.id)
        .where(
            PlaceQuestion.verifying_knowledge_id == category_knowledge_id,
            PlaceQuestion.active.is_(True),
        )
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none() is not None


def _build_first_ask_text(location_name: str, category_display_name: str) -> str:
    return f"What is {location_name} known for, when it comes to {category_display_name.lower()}?"


def _build_reverification_text(
    location_name: str, category_display_name: str, knowledge_text: str
) -> str:
    # Deliberately NOT a verbatim repeat of the original question (see the
    # architecture doc's Part 11) -- re-asking the identical question reads as
    # if the system forgot the answer. This names what we currently believe
    # and asks whether it still holds, which reads as "we remembered, we're
    # just confirming."
    return (
        f"Is {location_name} still like this — \"{knowledge_text}\" — or has that changed? "
        f"(Checking in on {category_display_name.lower()}.)"
    )


def _add_category_question(
    db: Session,
    *,
    location_id: UUID,
    text: str,
    category_assignment_id: UUID,
    verifying_knowledge_id: UUID | None,
    volatility: str,
    source_finding_id: UUID | None = None,
) -> bool:
    """Inserts one category-driven PlaceQuestion, honoring the SAME
    (location_id, normalized_text) uniqueness the AI-research/seed paths
    already rely on. Per-row savepoint (mirrors category_backfill.py's
    pattern): a collision here just means this exact question already exists
    under this Location -- skipped, not an error, never rolls back sibling
    inserts in the same run."""
    key = normalize_question(text)
    if not key:
        return False
    try:
        with db.begin_nested():
            db.add(
                PlaceQuestion(
                    location_id=location_id,
                    question_text=text,
                    normalized_text=key,
                    contribution_kind="observation",
                    category_assignment_id=category_assignment_id,
                    verifying_knowledge_id=verifying_knowledge_id,
                    volatility=volatility,
                    source_finding_id=source_finding_id,
                    source="ai_research",
                    active=True,
                )
            )
        return True
    except IntegrityError:
        return False


def _generate_grounded_first_ask(
    db: Session, location: Location, cov
) -> tuple[str, UUID | None] | None:
    """Tries to produce an LLM-phrased, research-grounded first-ask question
    for a MISSING category -- reusing existing Perplexity research first,
    performing at most one targeted query only when nothing existing is
    relevant (see category_research.get_or_create_category_finding), and
    NEVER treating the research as confirmed fact: this only ever produces
    a QUESTION, and the resulting PlaceQuestion's source_finding_id is
    provenance for "why was this asked", not evidence for CategoryKnowledge
    (only a moderated guide answer ever creates that -- see extractions.py).

    Returns None on ANY failure along the way -- no usable existing/targeted
    research, provider unavailable, provider error, or output that fails
    validation -- so the caller falls back to the deterministic template.
    That fallback is not a degraded mode; it is this feature's designed
    failure path (architecture directive Part 1E), and it is applied
    identically regardless of WHY grounding wasn't possible.
    """
    finding = category_research_service.get_or_create_category_finding(
        db, location, cov.slug, cov.display_name
    )
    if finding is None:
        return None
    try:
        text = anthropic_provider.generate_category_question(
            location.name, cov.display_name, finding.summary, finding.source_urls or []
        )
    except anthropic_provider.PlaceQuestionResearchProviderError:
        return None
    if not text:
        return None
    return text, finding.id


def generate_category_questions_for_location(
    db: Session, location_id: UUID, *, limit: int | None = None
) -> int:
    """Location -> category coverage -> missing/stale detection -> questions.

    For each category at/above the coverage relevance threshold:
      - MISSING (no verified knowledge) -> a first-ask question, UNLESS one is
        already open (never floods the same gap with duplicates).
      - STALE/PARTIALLY_STALE -> a re-verification question per stale item,
        referencing that item's id via verifying_knowledge_id, UNLESS one is
        already open for it.
      - FRESH -> nothing generated; a category with nothing to check needs no
        question (architecture doc Part 6/12).

    Bounded per call by settings.category_question_max_new_per_run so one
    under-covered Location can't flood a guide with a dozen questions at once.
    Best-effort per row (a normalized-text collision just skips that one
    question); commits once at the end. Returns the number of questions
    actually created.
    """
    location = db.get(Location, location_id)
    if location is None:
        return 0

    now = datetime.now(timezone.utc)
    coverage = category_knowledge_service.get_location_coverage(db, location_id, evaluation_time=now)
    cap = limit if limit is not None else settings.category_question_max_new_per_run

    created = 0
    for cov in coverage:
        if created >= cap:
            break

        if cov.state == category_knowledge_service.CATEGORY_STATE_MISSING:
            if _has_open_first_ask_question(db, cov.category_assignment_id):
                continue
            grounded = None
            try:
                grounded = _generate_grounded_first_ask(db, location, cov)
            except Exception:
                # Best-effort augmentation: any unexpected failure here must
                # never break generation for this (or any other) category --
                # falls through to the deterministic template exactly like a
                # handled failure would (Part 1E).
                logger.warning(
                    "Grounded category-question generation failed for %s / %s",
                    location_id, cov.slug, exc_info=True,
                )
                grounded = None
            if grounded is not None:
                text, source_finding_id = grounded
            else:
                text, source_finding_id = _build_first_ask_text(location.name, cov.display_name), None
            if _add_category_question(
                db,
                location_id=location_id,
                text=text,
                category_assignment_id=cov.category_assignment_id,
                verifying_knowledge_id=None,
                volatility=category_knowledge_policy.DEFAULT_VOLATILITY,
                source_finding_id=source_finding_id,
            ):
                created += 1
            continue

        if cov.state in (
            category_knowledge_service.CATEGORY_STATE_STALE,
            category_knowledge_service.CATEGORY_STATE_PARTIALLY_STALE,
        ):
            for item in cov.stale_items:
                if created >= cap:
                    break
                if category_knowledge_service.is_fresh(item, now):
                    continue  # only the STALE items within a partially-stale category
                if _has_open_reverification_question(db, item.id):
                    continue
                text = _build_reverification_text(location.name, cov.display_name, item.knowledge_text)
                if _add_category_question(
                    db,
                    location_id=location_id,
                    text=text,
                    category_assignment_id=cov.category_assignment_id,
                    verifying_knowledge_id=item.id,
                    volatility=item.volatility,
                ):
                    created += 1

    # Always committed, not just when created > 0: a research-grounding
    # attempt (category_research.get_or_create_category_finding) may have
    # persisted a new PlaceResearchFinding row even on a run that ultimately
    # added zero PlaceQuestions (e.g. every candidate collided with an
    # existing question) -- that finding row must survive to satisfy the
    # "never repeat a targeted query for the same (location, category)"
    # cost guarantee, so it cannot be left uncommitted for db.close() to
    # silently roll back.
    db.commit()
    return created


def maybe_generate_category_questions(db: Session, location_id: UUID) -> None:
    """Best-effort wrapper, same swallow-everything contract as
    maybe_ensure_researched below -- a failure here must never break whatever
    read triggered it."""
    try:
        generate_category_questions_for_location(db, location_id)
    except Exception:
        db.rollback()
        logger.warning(
            "Category-question generation failed for location %s", location_id, exc_info=True
        )


def hub_eligible_questions(
    db: Session, latitude: float, longitude: float
) -> list[PlaceQuestion]:
    """Active curated seed questions from any CURATED HUB the given
    coordinate falls within that hub's own eligibility radius of (see
    db/models/curated_hub.py).

    A hub's seed questions are stored as ordinary PlaceQuestion rows under
    the HUB's own location_id (its Area Location -- for the Thamel/Lukla
    launch data, the same real, Google-sourced Location the existing
    reverse-geocode mechanism already produces). Takes a raw coordinate
    rather than a Location object because a guide's SELECTED subject can be
    resolved either from a full Location row or from a slim
    NearestKnownPlace (see schemas/geographic_context.py) that never carries
    latitude/longitude -- this way neither caller has to fetch a Location
    it doesn't otherwise need just to ask "is this near a hub?".

    Distance is computed by PostGIS (ST_DWithin), the same convention every
    other geographic decision in this codebase already follows -- never
    Python math. The coordinate exactly at a hub's own anchor is included
    (distance 0 is always <= any positive radius), which is correct: a guide
    who chose "Thamel" itself should see Thamel's hub questions.
    """
    target = make_point(latitude, longitude)
    stmt = (
        select(PlaceQuestion)
        .join(CuratedHub, CuratedHub.location_id == PlaceQuestion.location_id)
        .join(Location, Location.id == CuratedHub.location_id)
        .where(
            PlaceQuestion.active.is_(True),
            PlaceQuestion.source == "seed",
            func.ST_DWithin(Location.geog, target, CuratedHub.radius_meters),
        )
        .order_by(PlaceQuestion.display_order, PlaceQuestion.created_at)
    )
    return list(db.execute(stmt).scalars().all())


def list_all_place_questions(
    db: Session, location_id: UUID, latitude: float, longitude: float
) -> list[PlaceQuestion]:
    """Every popular question a guide who selected/is at the Location
    identified by `location_id` should see: its own active questions
    (AI-researched and any curated seed questions specific to this exact
    place -- both already share one table and one `active` flag, so
    `list_place_questions` already returns both together) PLUS any curated
    hub's seed questions `(latitude, longitude)` falls within range of (see
    hub_eligible_questions). The coordinate is passed separately from the id
    because callers resolve it from different shapes (a full Location row,
    or the guide's own live position) and neither should have to fetch a
    Location purely to ask the hub-proximity question.

    Cross-source de-duplication happens HERE, once, by the same
    `normalized_text` key the database's own UNIQUE constraint is built on --
    reusing that exact key rather than a second comparison rule is what makes
    "prevent duplicate questions" mean the same thing everywhere in this
    system. Own-Location questions always win a collision (they are strictly
    more specific than a hub-wide question), so ties are resolved in the
    order the task itself describes: "Selected Location questions + curated
    seed questions".
    """
    own = list_place_questions(db, location_id)
    hub = hub_eligible_questions(db, latitude, longitude)

    seen = {q.normalized_text for q in own}
    merged = list(own)
    for question in hub:
        if question.normalized_text in seen:
            continue
        seen.add(question.normalized_text)
        merged.append(question)
    return merged


def is_abandoned(research: PlaceQuestionResearch) -> bool:
    """True when a run claims to be 'processing' but cannot still be running.

    The claim in ensure_researched refuses to start a second run while one is
    'processing' -- correct, it prevents paying twice for the same web search.
    But nothing resets that flag if the process holding it dies: a crash, a
    container restart, or a deploy mid-run leaves the row stuck, and that place
    is then locked out of research PERMANENTLY. The failure is invisible: the
    app simply never gets invitations there and looks generic forever.

    The cutoff is the provider timeout plus a margin, past which the original
    attempt has either finished (and would have moved the status) or can no
    longer be alive.
    """
    if research.status != "processing":
        return False
    started = research.started_at
    if started is None:
        return True
    age = datetime.now(timezone.utc) - started
    return age.total_seconds() > settings.place_question_research_timeout_seconds + 120


def is_research_stale(research: PlaceQuestionResearch | None) -> bool:
    """True when a (re)search is due: never researched, or the last SUCCESSFUL
    run is older than the configured window. A row stuck in 'failed' with no
    researched_at is stale, so retries remain possible -- but a row currently
    'processing' is NOT restarted here (see ensure_researched)."""
    if research is None or research.researched_at is None:
        return True
    age = datetime.now(timezone.utc) - research.researched_at
    return age > timedelta(days=settings.place_question_refresh_days)


def _ensure_research_row(db: Session, location_id: UUID) -> PlaceQuestionResearch:
    """Get-or-create, race-safe via the UNIQUE constraint on location_id --
    the same IntegrityError-catch-and-refetch pattern as
    knowledge_types.create_or_get_dynamic_type (an INSERT race cannot be
    solved with SELECT FOR UPDATE, since there is no row to lock yet)."""
    existing = get_research(db, location_id)
    if existing is not None:
        return existing
    research = PlaceQuestionResearch(location_id=location_id, status="pending")
    db.add(research)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = get_research(db, location_id)
        if existing is None:
            raise
        return existing
    return research


def _resolve_locality(db: Session, location: Location) -> str | None:
    """The place's locality ("Koramangala, Bengaluru"), resolving and storing it
    the first time it is needed.

    Not merely nice-to-have context: research for a place named "Ganesh Temple"
    is worthless without it and accurate with it. Resolved lazily rather than at
    creation so manually-curated Locations, which predate this column, pick one
    up on their first research run instead of needing a backfill that would have
    to guess.

    Best-effort: a failure returns None and research proceeds on the name alone,
    which is worse but not broken.
    """
    if location.locality:
        return location.locality
    locality = get_place_provider().reverse_geocode_locality(
        float(location.latitude), float(location.longitude)
    )
    if locality:
        location.locality = locality
        db.commit()
        logger.info("Resolved locality for %r: %s", location.name, locality)
    return locality


def _previously_asked(db: Session, location_id: UUID) -> list[str]:
    """Every invitation ever generated for this place, active or superseded.

    Given to the generation step so it does not re-ask what a guide has already
    been asked. Deliberately includes INACTIVE questions: a question retired by
    a previous refresh was still put in front of someone, and re-proposing it
    would just cycle the same few ideas forever. The UNIQUE (location_id,
    normalized_text) constraint would catch exact repeats anyway -- this catches
    the rephrasings it cannot.
    """
    stmt = (
        select(PlaceQuestion.question_text)
        .where(PlaceQuestion.location_id == location_id)
        .order_by(PlaceQuestion.created_at.desc())
        .limit(30)
    )
    return list(db.execute(stmt).scalars().all())


def _persist_findings(
    db: Session,
    location_id: UUID,
    research_id: UUID,
    findings: list[ResearchFinding],
) -> dict[str, PlaceResearchFinding]:
    """Stores what research actually found, keyed by topic for the questions
    that will cite it.

    Written BEFORE generation runs, so provenance exists even if generation then
    fails -- the evidence was really retrieved either way, and the next attempt
    can be diagnosed against it.
    """
    stored: dict[str, PlaceResearchFinding] = {}
    for finding in findings:
        row = PlaceResearchFinding(
            location_id=location_id,
            research_id=research_id,
            topic=finding.topic,
            query_text=finding.query,
            provider=finding.provider,
            model=finding.model,
            summary=finding.summary,
            source_urls=finding.source_urls or None,
            source_titles=finding.source_titles or None,
            retrieved_at=finding.retrieved_at,
            input_tokens=finding.input_tokens,
            output_tokens=finding.output_tokens,
            cost_usd=finding.cost_usd,
        )
        db.add(row)
        stored[finding.topic] = row
    db.flush()
    return stored


def _persist_questions(
    db: Session,
    location_id: UUID,
    researched: list[validation.ResearchedQuestion],
    findings_by_topic: dict[str, PlaceResearchFinding] | None = None,
) -> int:
    """Replaces this place's active AI-RESEARCHED question set with the new
    batch. Curated seed questions (PlaceQuestion.source == 'seed') for this
    same Location are never read, deactivated or touched by this function in
    any way -- they are a different provenance with a different owner
    (services/seed_import.py), and a research refresh superseding its OWN
    previous batch must never be able to silently retire someone else's
    curated content. See PLACE_QUESTION_SOURCES's own comment.

    Superseded AI questions are DEACTIVATED, never deleted: a question that
    has already been answered must keep existing so the answer's provenance
    (submissions.source_place_question_id) still resolves to something real.

    In-batch duplicates are dropped by normalized key before insert, and the
    UNIQUE (location_id, normalized_text) constraint is the backstop -- a
    reactivating UPDATE handles the case where this exact question already
    exists from a previous AI batch, so a refresh never fails on a repeat.
    The one case that update path deliberately does NOT cover is a text
    collision against a SEED question (same location, same normalized text,
    but source == 'seed') -- that row is left exactly as it is and the
    AI-generated duplicate of it is simply skipped, because inserting would
    violate the same UNIQUE constraint and overwriting would mean an
    automated run quietly replacing a human curator's question.
    """
    batch_id = uuid.uuid4()

    # Nothing usable came back. Keep the existing set exactly as it is rather
    # than retiring it for a replacement that does not exist: those questions
    # are still the best thing we have to ask about this place, and a guide
    # standing there can still confirm whether they hold. Wiping them would
    # turn "our information has aged" into "we have no information", which is
    # strictly worse and not what the run discovered.
    if not researched:
        logger.info(
            "Research for %s produced no usable questions -- keeping the existing set.",
            location_id,
        )
        return 0

    all_existing = db.execute(
        select(PlaceQuestion).where(PlaceQuestion.location_id == location_id)
    ).scalars().all()
    # Keyed for the update-in-place path below -- AI rows only, so a seed
    # row can never be mistaken for "the previous batch's version" of a
    # freshly generated question.
    existing_ai_by_key = {q.normalized_text: q for q in all_existing if q.source == "ai_research"}
    # Keyed only to detect (and skip) a collision against curated content --
    # never written to.
    seed_keys = {q.normalized_text for q in all_existing if q.source == "seed"}
    for question in existing_ai_by_key.values():
        question.active = False

    seen: set[str] = set()
    kept = 0
    for order, item in enumerate(researched):
        key = normalize_question(item.question_text)
        if not key or key in seen:
            continue
        seen.add(key)
        if key in seed_keys:
            # A curator already asked this exact question for this place.
            # The seed row stands; nothing to add.
            continue
        if kept >= settings.place_question_max_count:
            break

        source_urls = item.source_urls or None
        # Links the invitation to the exact finding it was drawn from, so
        # "why did TrailMind ask this?" resolves to a stored query, summary and
        # citation list rather than to a model call that has already ended.
        finding = (findings_by_topic or {}).get(item.finding_topic or "")
        finding_id = finding.id if finding is not None else None

        existing = existing_ai_by_key.get(key)
        if existing is not None:
            existing.question_text = item.question_text
            existing.contribution_kind = item.contribution_kind
            existing.context_note = item.context_note
            existing.display_order = order
            existing.source_urls = source_urls
            existing.source_finding_id = finding_id
            existing.research_batch_id = batch_id
            existing.active = True
        else:
            db.add(
                PlaceQuestion(
                    location_id=location_id,
                    question_text=item.question_text,
                    normalized_text=key,
                    contribution_kind=item.contribution_kind,
                    context_note=item.context_note,
                    display_order=order,
                    source_urls=source_urls,
                    source_finding_id=finding_id,
                    research_batch_id=batch_id,
                    source="ai_research",
                    active=True,
                )
            )
        kept += 1
    return kept


def ensure_researched(db: Session, location_id: UUID, force: bool = False) -> PlaceQuestionResearch:
    """Researches this place's popular questions if due (or if forced).

    Returns the research row in its resulting state. A 'failed' outcome is a
    legitimate, honest result -- callers should still serve whatever questions
    already exist rather than erroring, because stale questions beat none.
    """
    location = db.get(Location, location_id)
    if location is None:
        raise LookupError(f"Location {location_id} not found")

    research = _ensure_research_row(db, location_id)
    db.commit()

    # Claim: re-read under a row lock so two concurrent callers cannot both
    # start a web search for the same place.
    locked = db.execute(
        select(PlaceQuestionResearch)
        .where(PlaceQuestionResearch.id == research.id)
        .with_for_update()
    ).scalar_one()

    if locked.status == "processing" and not is_abandoned(locked):
        # Another request is genuinely still researching this place. Don't
        # duplicate the web spend; the caller serves existing questions.
        db.commit()
        return locked

    if is_abandoned(locked):
        # A previous attempt died holding the claim. Reclaimed rather than
        # left stuck forever; logged because repeated reclaims mean runs are
        # dying and that is worth noticing.
        logger.warning(
            "Reclaiming abandoned place-question research for %s (started %s).",
            location_id,
            locked.started_at,
        )

    if not force and not is_research_stale(locked):
        db.commit()
        return locked

    # Resolved before the claim is taken, so the (cheap, cached) geocode is not
    # counted against the run's abandoned-run timeout.
    locality = _resolve_locality(db, location)

    locked.status = "processing"
    locked.attempt_count += 1
    locked.started_at = datetime.now(timezone.utc)
    locked.error_message = None
    # Both halves recorded: research and generation are different providers now,
    # and a run's provenance should say so.
    locked.provider = f"{perplexity_provider.PROVIDER_NAME}+anthropic"
    locked.model = settings.anthropic_model
    # Releases the row lock BEFORE the external calls -- the lock exists to
    # serialize claiming, not to be held across a multi-second web search.
    db.commit()

    place_name = location.name
    latitude = float(location.latitude)
    longitude = float(location.longitude)
    description = location.description
    place_kind = location.place_kind

    def _fail(exc: Exception) -> PlaceQuestionResearch:
        failed = db.get(PlaceQuestionResearch, research.id)
        failed.status = "failed"
        failed.error_message = str(getattr(exc, "message", exc))[:500]
        failed.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.warning(
            "Place question research failed for %s: %s", location_id, type(exc).__name__
        )
        return failed

    # --- 1. RESEARCH: what does the web actually say about this exact place? --
    try:
        provider = perplexity_provider.get_provider()
        findings = research_plan.run_research_plan(
            provider, place_name, place_kind, locality
        )
    except ResearchProviderError as exc:
        return _fail(exc)

    findings_by_topic = _persist_findings(db, location_id, research.id, findings)
    db.commit()

    if not findings:
        # An honest, common outcome: most places on earth are not written
        # about. Recorded as a SUCCESSFUL run with zero questions rather than a
        # failure -- a failure would be retried on every request forever, and
        # there is nothing to retry. No generation call is made, which is also
        # the cheapest possible handling of the commonest case.
        done = db.get(PlaceQuestionResearch, research.id)
        done.status = "completed"
        done.error_message = None
        completed_at = datetime.now(timezone.utc)
        done.completed_at = completed_at
        done.researched_at = completed_at
        db.commit()
        logger.info("No usable research for location %s -- no questions generated.", location_id)
        return done

    # --- 2. GENERATION: which of those details can someone here check? -------
    # Only URLs genuinely retrieved above are citable. This is what makes a
    # question's provenance a fact rather than a claim -- see
    # validation._keep_only_cited_urls.
    allowed_urls = {url for finding in findings for url in finding.source_urls}
    try:
        raw = anthropic_provider.generate_place_questions(
            place_name,
            latitude,
            longitude,
            description,
            locality,
            findings,
            _previously_asked(db, location_id),
            location.category,
            location.subcategory,
            category_assignment.describe_categories_for_prompt(
                category_assignment.list_location_categories(db, location_id)
            ),
        )
        researched = validation.validate_research_output(raw, allowed_urls)
    except (
        anthropic_provider.PlaceQuestionResearchProviderError,
        validation.ResearchValidationError,
    ) as exc:
        return _fail(exc)

    kept = _persist_questions(db, location_id, researched, findings_by_topic)

    done = db.get(PlaceQuestionResearch, research.id)
    done.status = "completed"
    done.error_message = None
    completed_at = datetime.now(timezone.utc)
    done.completed_at = completed_at
    # Only a SUCCESSFUL run moves researched_at -- so a string of failures can
    # never masquerade as fresh research and suppress future attempts.
    done.researched_at = completed_at
    db.commit()

    logger.info("Researched %d popular question(s) for location %s.", kept, location_id)
    return done


def maybe_ensure_researched(db: Session, location_id: UUID) -> None:
    """Best-effort trigger for read paths (the mobile question list). Never
    raises: a research failure must not break a guide's question list, which
    should still render whatever is already known. Mirrors
    extractions.maybe_trigger_extraction's swallow-everything contract."""
    try:
        ensure_researched(db, location_id)
    except Exception as exc:  # noqa: BLE001 -- deliberate best-effort boundary
        logger.warning(
            "Best-effort place question research failed for %s: %s",
            location_id,
            type(exc).__name__,
        )


def place_question_reward_points(db: Session, contribution_kind: str | None = None) -> int:
    """What contributing to a place question is currently worth, for its KIND.

    Resolved from the reward_rules table so the app is never the one deciding,
    and per-kind so a photo request and a "is it open?" check aren't paid the
    same (see rewards.place_question_rule_key)."""
    return reward_service.resolve_place_question_points(db, contribution_kind)
