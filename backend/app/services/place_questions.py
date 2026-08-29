"""Place-specific invitations -- the SECOND question source.

Nothing in this module touches the knowledge-gap pipeline. It never reads
KnowledgeTypeConfig, never evaluates knowledge state, never ranks a gap, and
never creates a Question/QuestionAssignment row. These are a parallel,
secondary source that the mobile app renders BELOW the gap queue. The two
systems answer different questions:

    Questions queue -- "what does TrailMind not know yet?"   (gap-driven)
    Place questions -- "this person is standing HERE, now"   (presence-driven)

THE THREE-SOURCE CHAIN THIS ORCHESTRATES

    OpenStreetMap  ->  what physically exists here, and where
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

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.location import Location
from app.db.models.place_question import PlaceQuestion, PlaceQuestionResearch
from app.db.models.place_research_finding import PlaceResearchFinding
from app.services import rewards as reward_service
from app.services.place_question_research import (
    anthropic_provider,
    research_plan,
    validation,
)
from app.services.poi_discovery_research import osm_provider
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
    locality = osm_provider.reverse_geocode_locality(
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
    """Replaces this place's active question set with the new batch.

    Superseded questions are DEACTIVATED, never deleted: a question that has
    already been answered must keep existing so the answer's provenance
    (submissions.source_place_question_id) still resolves to something real.

    In-batch duplicates are dropped by normalized key before insert, and the
    UNIQUE (location_id, normalized_text) constraint is the backstop -- a
    reactivating UPDATE handles the case where this exact question already
    exists from a previous batch, so a refresh never fails on a repeat.
    """
    batch_id = uuid.uuid4()

    existing_by_key = {
        q.normalized_text: q
        for q in db.execute(
            select(PlaceQuestion).where(PlaceQuestion.location_id == location_id)
        ).scalars().all()
    }
    for question in existing_by_key.values():
        question.active = False

    seen: set[str] = set()
    kept = 0
    for order, item in enumerate(researched):
        key = normalize_question(item.question_text)
        if not key or key in seen:
            continue
        seen.add(key)
        if kept >= settings.place_question_max_count:
            break

        source_urls = item.source_urls or None
        # Links the invitation to the exact finding it was drawn from, so
        # "why did TrailMind ask this?" resolves to a stored query, summary and
        # citation list rather than to a model call that has already ended.
        finding = (findings_by_topic or {}).get(item.finding_topic or "")
        finding_id = finding.id if finding is not None else None

        existing = existing_by_key.get(key)
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
