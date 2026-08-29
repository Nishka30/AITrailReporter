"""Popular questions for a place (Step 18) -- the SECOND question source.

Nothing in this module touches the knowledge-gap pipeline. It never reads
KnowledgeTypeConfig, never evaluates knowledge state, never ranks a gap, and
never creates a Question/QuestionAssignment row. Popular questions are a
parallel, secondary source that the mobile app renders BELOW the gap queue.

Concurrency follows the established pattern from extractions.py/questions.py:
the research row is claimed under SELECT ... FOR UPDATE, and the lock is
RELEASED BEFORE the LLM/web call -- a slow external call must never hold a
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
from app.services import rewards as reward_service
from app.services.place_question_research import anthropic_provider, validation

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


def _persist_questions(
    db: Session,
    location_id: UUID,
    researched: list[validation.ResearchedQuestion],
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
        existing = existing_by_key.get(key)
        if existing is not None:
            existing.question_text = item.question_text
            existing.contribution_kind = item.contribution_kind
            existing.context_note = item.context_note
            existing.display_order = order
            existing.source_urls = source_urls
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

    if locked.status == "processing":
        # Another request is already researching this place. Don't duplicate
        # the web spend; the caller serves existing questions meanwhile.
        db.commit()
        return locked

    if not force and not is_research_stale(locked):
        db.commit()
        return locked

    locked.status = "processing"
    locked.attempt_count += 1
    locked.started_at = datetime.now(timezone.utc)
    locked.error_message = None
    locked.model = settings.anthropic_model
    # Releases the row lock BEFORE the external call -- the lock exists to
    # serialize claiming, not to be held across a multi-second web search.
    db.commit()

    place_name = location.name
    latitude = float(location.latitude)
    longitude = float(location.longitude)
    description = location.description

    try:
        raw = anthropic_provider.research_place_questions(
            place_name, latitude, longitude, description
        )
        researched = validation.validate_research_output(raw)
    except (
        anthropic_provider.PlaceQuestionResearchProviderError,
        validation.ResearchValidationError,
    ) as exc:
        failed = db.get(PlaceQuestionResearch, research.id)
        failed.status = "failed"
        failed.error_message = str(getattr(exc, "message", exc))[:500]
        failed.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.warning("Place question research failed for %s: %s", location_id, type(exc).__name__)
        return failed

    kept = _persist_questions(db, location_id, researched)

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
