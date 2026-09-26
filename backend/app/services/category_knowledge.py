"""CategoryKnowledge -- the PRIMARY knowledge system (Location -> Categories
-> CategoryKnowledge -> Questions -> Verification -> Fresh/Stale/Missing).

This module owns:
  - creating a knowledge item (pending, unverified) from a guide's answer
  - marking one verified (called from observation_moderation on approval --
    the ONE trigger for last_verified_at, see category_knowledge.py's model
    docstring)
  - deriving category coverage state (MISSING/FRESH/STALE/PARTIALLY_STALE)
    for a Location, for both question-generation and Admin/API reads

Nothing here touches KnowledgeTypeConfig, Question, or knowledge_state.py --
those remain the separate, narrower hazard-exception system. Nothing here
duplicates location_categories/location_category_assignments -- that stays
the single category taxonomy, reused as-is.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.category_knowledge import CategoryKnowledge
from app.db.models.category_knowledge_conflict import (
    CONFLICT_RESOLUTIONS,
    CategoryKnowledgeConflict,
)
from app.db.models.location_category import LocationCategory, LocationCategoryAssignment
from app.services import category_knowledge_policy

# Category coverage/freshness states -- derived, never stored (see the model
# docstring for why: nothing sweeps this table on a schedule, so a stored
# status column would be a second, driftable source of truth).
CATEGORY_STATE_MISSING = "missing"
CATEGORY_STATE_FRESH = "fresh"
CATEGORY_STATE_STALE = "stale"
CATEGORY_STATE_PARTIALLY_STALE = "partially_stale"


def stale_at(item: CategoryKnowledge) -> datetime | None:
    """The instant this item expires, or None if it has never been verified
    (an unverified item has no freshness clock running yet -- it simply
    doesn't count toward coverage at all, see is_verified below)."""
    if item.last_verified_at is None:
        return None
    return item.last_verified_at + timedelta(hours=item.freshness_duration_hours)


def is_verified(item: CategoryKnowledge) -> bool:
    """A row counts toward coverage only once a trusted guide's answer has
    actually cleared moderation -- a pending/unverified row (last_verified_at
    still NULL) does not count, so two guides answering the same missing-
    knowledge question before either is moderated can't silently double-cover
    a category from unverified content."""
    return item.last_verified_at is not None


def is_fresh(item: CategoryKnowledge, now: datetime) -> bool:
    expiry = stale_at(item)
    return is_verified(item) and expiry is not None and now <= expiry


def is_stale(item: CategoryKnowledge, now: datetime) -> bool:
    return is_verified(item) and not is_fresh(item, now)


def compute_category_state(items: list[CategoryKnowledge], now: datetime) -> str:
    """The four-state rollup for one category's knowledge items. Only VERIFIED
    items are considered at all -- a category with three pending-unverified
    items and zero verified ones is still MISSING, not covered."""
    verified = [item for item in items if item.active and is_verified(item)]
    if len(verified) < settings.category_coverage_min_verified_items:
        return CATEGORY_STATE_MISSING
    fresh_count = sum(1 for item in verified if is_fresh(item, now))
    if fresh_count == len(verified):
        return CATEGORY_STATE_FRESH
    if fresh_count == 0:
        return CATEGORY_STATE_STALE
    return CATEGORY_STATE_PARTIALLY_STALE


@dataclass
class CategoryCoverage:
    """One assigned category's current knowledge state for one Location --
    the unit both question-generation and Admin/API reads operate on."""

    category_assignment_id: UUID
    category_id: UUID
    slug: str
    kind: str
    display_name: str
    relevance: int
    is_primary: bool
    state: str
    items: list[CategoryKnowledge] = field(default_factory=list)

    @property
    def stale_items(self) -> list[CategoryKnowledge]:
        return [i for i in self.items if i.active and is_verified(i)]


def get_location_coverage(
    db: Session, location_id: UUID, *, evaluation_time: datetime | None = None
) -> list[CategoryCoverage]:
    """Every category assignment at/above the configured relevance threshold
    for this Location, each with its derived coverage state -- the read both
    question generation (missing/stale detection) and Admin/API status reuse.

    Only assignments meeting settings.category_coverage_min_relevance count:
    a low-relevance theme (e.g. a barely-applicable 'nightlife' tag on a
    trailhead) would otherwise generate noise questions nobody wants to ask
    or answer (see the module docstring / architecture doc Part 16).
    """
    now = evaluation_time or datetime.now(timezone.utc)

    assignments = list(
        db.execute(
            select(LocationCategoryAssignment, LocationCategory)
            .join(LocationCategory, LocationCategory.id == LocationCategoryAssignment.category_id)
            .where(
                LocationCategoryAssignment.location_id == location_id,
                LocationCategoryAssignment.relevance >= settings.category_coverage_min_relevance,
                LocationCategory.active.is_(True),
            )
            .order_by(LocationCategoryAssignment.relevance.desc())
        ).all()
    )
    if not assignments:
        return []

    assignment_ids = [a.id for a, _c in assignments]
    items_by_assignment: dict[UUID, list[CategoryKnowledge]] = {aid: [] for aid in assignment_ids}
    for item in db.execute(
        select(CategoryKnowledge).where(
            CategoryKnowledge.category_assignment_id.in_(assignment_ids),
            CategoryKnowledge.active.is_(True),
        )
    ).scalars():
        items_by_assignment[item.category_assignment_id].append(item)

    coverage: list[CategoryCoverage] = []
    for assignment, category in assignments:
        items = items_by_assignment[assignment.id]
        coverage.append(
            CategoryCoverage(
                category_assignment_id=assignment.id,
                category_id=category.id,
                slug=category.slug,
                kind=category.kind,
                display_name=category.display_name,
                relevance=assignment.relevance,
                is_primary=assignment.is_primary,
                state=compute_category_state(items, now),
                items=items,
            )
        )
    return coverage


def get_category_labels_for_assignments(
    db: Session, assignment_ids: list[UUID]
) -> dict[UUID, tuple[str, str]]:
    """Batch lookup: assignment_id -> (slug, display_name), for mobile
    "About this place" category grouping (see api/routes/place_questions.py
    and guides.py). One query for a whole page of questions, never one per
    question -- same N+1-avoidance convention as every other batched read in
    this codebase."""
    if not assignment_ids:
        return {}
    rows = db.execute(
        select(LocationCategoryAssignment.id, LocationCategory.slug, LocationCategory.display_name)
        .join(LocationCategory, LocationCategory.id == LocationCategoryAssignment.category_id)
        .where(LocationCategoryAssignment.id.in_(assignment_ids))
    ).all()
    return {row[0]: (row[1], row[2]) for row in rows}


def create_knowledge_item(
    db: Session,
    *,
    location_id: UUID,
    category_assignment_id: UUID,
    knowledge_text: str,
    volatility: str,
    source_question_id: UUID | None = None,
    source_finding_id: UUID | None = None,
    source: str = "ai_research",
) -> CategoryKnowledge:
    """Creates a new, PENDING (unverified) knowledge item -- last_verified_at
    stays NULL until moderation approves the Observation that carries it (see
    mark_verified). freshness_duration_hours is snapshotted here, from the
    volatility class, never re-read live afterward."""
    item = CategoryKnowledge(
        location_id=location_id,
        category_assignment_id=category_assignment_id,
        knowledge_text=knowledge_text,
        volatility=volatility,
        freshness_duration_hours=category_knowledge_policy.resolve_freshness_duration_hours(volatility),
        source_question_id=source_question_id,
        source_finding_id=source_finding_id,
        source=source,
        active=True,
    )
    db.add(item)
    db.flush()
    return item


def get_knowledge_item(db: Session, category_knowledge_id: UUID) -> CategoryKnowledge | None:
    return db.get(CategoryKnowledge, category_knowledge_id)


def mark_verified(db: Session, category_knowledge_id: UUID, verified_at: datetime) -> CategoryKnowledge | None:
    """THE one place last_verified_at is ever set -- called only from
    observation_moderation.py when an Observation carrying category_knowledge_id
    is approved (or a prior decision is changed TO approved). Never called by
    question generation, a raw answer, extraction, or Perplexity research."""
    item = get_knowledge_item(db, category_knowledge_id)
    if item is None:
        return None
    item.last_verified_at = verified_at
    db.flush()
    return item


def supersede_knowledge_item(
    db: Session,
    *,
    old_item: CategoryKnowledge,
    new_knowledge_text: str,
    volatility: str,
    source_question_id: UUID | None,
    verified_at: datetime,
) -> CategoryKnowledge:
    """A later verification CONTRADICTS (not merely reconfirms) old_item --
    e.g. a guide reports the fact is no longer true. old_item is deactivated
    and left exactly as it was (full history preserved via its own
    Observations); a new, already-verified row replaces it. Never edits
    old_item's knowledge_text in place -- that would destroy the history this
    design explicitly preserves."""
    new_item = CategoryKnowledge(
        location_id=old_item.location_id,
        category_assignment_id=old_item.category_assignment_id,
        knowledge_text=new_knowledge_text,
        volatility=volatility,
        freshness_duration_hours=category_knowledge_policy.resolve_freshness_duration_hours(volatility),
        last_verified_at=verified_at,
        source_question_id=source_question_id,
        source=old_item.source,
        active=True,
    )
    db.add(new_item)
    db.flush()
    old_item.superseded_by_id = new_item.id
    old_item.active = False
    db.flush()
    return new_item


# ---------------------------------------------------------------------------
# Contradiction-handling resolution queue (Part 2 of the knowledge-
# architecture hardening pass). See app/services/knowledge_relation.py for
# the CONFIRMS/CONTRADICTS/UNCERTAIN judgement itself -- this section only
# ever records/resolves the UNCERTAIN outcome. CONFIRMS and CONTRADICTS are
# applied directly by observation_moderation.py via mark_verified/
# supersede_knowledge_item above; they never pass through here.
# ---------------------------------------------------------------------------


def record_conflict(
    db: Session, *, category_knowledge_id: UUID, observation_id: UUID, new_answer_text: str
) -> CategoryKnowledgeConflict:
    """Opens an explicit, admin-visible conflict for an UNCERTAIN
    relationship -- the existing CategoryKnowledge row is left completely
    untouched (see the class docstring on CategoryKnowledgeConflict)."""
    conflict = CategoryKnowledgeConflict(
        category_knowledge_id=category_knowledge_id,
        observation_id=observation_id,
        new_answer_text=new_answer_text,
        status="open",
    )
    db.add(conflict)
    db.flush()
    return conflict


def list_open_conflicts(db: Session) -> list[CategoryKnowledgeConflict]:
    stmt = (
        select(CategoryKnowledgeConflict)
        .where(CategoryKnowledgeConflict.status == "open")
        .order_by(CategoryKnowledgeConflict.created_at.desc())
    )
    return list(db.execute(stmt).scalars().all())


class ConflictNotFoundError(Exception):
    def __init__(self, conflict_id: UUID):
        self.conflict_id = conflict_id
        super().__init__(f"CategoryKnowledgeConflict {conflict_id} not found")


def resolve_conflict(
    db: Session,
    conflict_id: UUID,
    *,
    resolution: str,
    resolved_by: str,
    new_knowledge_text: str | None = None,
    volatility: str | None = None,
) -> CategoryKnowledgeConflict:
    """The one admin-facing action on an open conflict -- mirrors
    observation_moderation.approve/reject's idempotent-on-repeat contract
    (an already-resolved conflict is a no-op, not an error).

    resolution == 'confirmed'  -> mark_verified on the EXISTING row (the
                                   admin judged this a reconfirmation after
                                   all).
    resolution == 'superseded' -> supersede_knowledge_item using
                                   new_knowledge_text (required) -- the admin
                                   judged this a real contradiction.
    resolution == 'dismissed'  -> neither; the conflict is simply closed
                                   (e.g. the new answer was genuinely bad
                                   evidence, not a knowledge change at all).
    """
    conflict = db.get(CategoryKnowledgeConflict, conflict_id)
    if conflict is None:
        raise ConflictNotFoundError(conflict_id)
    if conflict.status == "resolved":
        return conflict

    if resolution not in CONFLICT_RESOLUTIONS:
        raise ValueError(f"Unknown resolution: {resolution!r}")

    now = datetime.now(timezone.utc)
    item = db.get(CategoryKnowledge, conflict.category_knowledge_id)
    if item is None:
        raise LookupError(f"CategoryKnowledge {conflict.category_knowledge_id} not found")

    if resolution == "confirmed":
        mark_verified(db, item.id, now)
    elif resolution == "superseded":
        if not new_knowledge_text or not new_knowledge_text.strip():
            raise ValueError("new_knowledge_text is required to supersede this knowledge item.")
        # The Admin may only ever choose the volatility CLASS (defaulting to
        # the existing item's own class when not overridden) -- the backend
        # remains the sole authority on what duration that maps to (see
        # supersede_knowledge_item -> category_knowledge_policy.
        # resolve_freshness_duration_hours). There is no path anywhere in
        # this function, or the API schema calling it, that accepts a raw
        # freshness_duration_hours from a client.
        resolved_volatility = volatility or item.volatility
        try:
            new_item = supersede_knowledge_item(
                db,
                old_item=item,
                new_knowledge_text=new_knowledge_text.strip(),
                volatility=resolved_volatility,
                source_question_id=item.source_question_id,
                verified_at=now,
            )
        except category_knowledge_policy.InvalidVolatilityError as exc:
            raise ValueError(exc.message) from exc
        conflict.resolved_knowledge_id = new_item.id
    # 'dismissed' mutates nothing else -- the CategoryKnowledge row stands
    # exactly as it was before this conflict was ever raised.

    conflict.status = "resolved"
    conflict.resolution = resolution
    conflict.resolved_by = resolved_by
    conflict.resolved_at = now
    db.commit()
    db.refresh(conflict)
    return conflict
