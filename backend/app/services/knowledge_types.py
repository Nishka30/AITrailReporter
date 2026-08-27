from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.knowledge_type_config import KnowledgeTypeConfig
from app.services.knowledge_type_policy import ResolvedTypePolicy


def get_knowledge_type_by_name(db: Session, knowledge_type: str) -> KnowledgeTypeConfig | None:
    """Lookup by name REGARDLESS of active flag -- deliberately distinct from
    get_active_knowledge_type_by_name below. Used by dynamic type creation
    (Step 16), which must see a deactivated row so it never tries to INSERT a
    duplicate name that the unique constraint would reject."""
    stmt = select(KnowledgeTypeConfig).where(
        KnowledgeTypeConfig.knowledge_type == knowledge_type
    )
    return db.execute(stmt).scalar_one_or_none()


def create_or_get_dynamic_type(
    db: Session, policy: ResolvedTypePolicy
) -> tuple[KnowledgeTypeConfig, bool]:
    """Creates a KnowledgeTypeConfig from an already-validated, deterministically
    resolved policy (see app/services/knowledge_type_policy.py), or returns the
    existing row if this normalized knowledge_type name is already taken.
    Returns (config, created).

    Existing-row semantics, both deliberate:
      - An ACTIVE existing type is simply reused. This is the "the model
        rediscovered a category we already have" case and is the common,
        healthy outcome -- not an error.
      - An INACTIVE existing type is ALSO reused, and is NEVER reactivated.
        `active` is a human/administrative decision; an LLM proposal must not
        be able to silently undo it. The observation still gets recorded
        against that type, so the guide's contribution is never discarded --
        it simply doesn't participate in knowledge-state evaluation until an
        administrator reactivates the type (knowledge_state.py reads active
        types only).

    Race safety: the real guarantee is the DB unique constraint on
    knowledge_type (see the model). Two concurrent extractions proposing the
    SAME new category both miss the initial SELECT, both attempt the INSERT,
    and exactly one wins -- the loser catches IntegrityError, rolls back, and
    re-fetches the winner's row, the identical pattern used by
    guides.create_or_get_guide and submissions.create_or_get_submission. This
    is an INSERT race, so IntegrityError-catch-and-refetch is the correct
    pattern here -- not SELECT ... FOR UPDATE, which cannot lock a row that
    does not exist yet.
    """
    existing = get_knowledge_type_by_name(db, policy.knowledge_type)
    if existing is not None:
        return existing, False

    config = KnowledgeTypeConfig(
        knowledge_type=policy.knowledge_type,
        display_name=policy.display_name,
        freshness_window_hours=policy.freshness_window_hours,
        aging_threshold_hours=policy.aging_threshold_hours,
        geographic_relevance_radius_meters=policy.geographic_relevance_radius_meters,
        default_priority=policy.default_priority,
        safety_critical=policy.safety_critical,
        # Created ACTIVE on purpose: the whole point of Case B is that the new
        # category immediately joins the fresh -> aging -> stale -> gap ->
        # question lifecycle (Step 10/11/12 all read active types only). A type
        # created inactive would be inert and would silently never generate the
        # future questions that justify creating it at all.
        active=True,
    )
    db.add(config)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = get_knowledge_type_by_name(db, policy.knowledge_type)
        if existing is None:
            raise
        return existing, False
    return config, True


def get_active_knowledge_types(db: Session) -> list[KnowledgeTypeConfig]:
    """The only knowledge types an LLM extraction is ever allowed to use (Step 9).
    Database configuration is the source of truth -- the caller must never fall
    back to a hardcoded list if this comes back empty."""
    stmt = (
        select(KnowledgeTypeConfig)
        .where(KnowledgeTypeConfig.active.is_(True))
        .order_by(KnowledgeTypeConfig.knowledge_type)
    )
    return list(db.execute(stmt).scalars().all())


def get_active_knowledge_type_by_name(db: Session, knowledge_type: str) -> KnowledgeTypeConfig | None:
    """Used by Step 12 question generation to resolve a caller-supplied
    knowledge_type string before doing anything else -- an inactive or unknown
    type is rejected immediately, never silently treated as a valid gap
    target."""
    stmt = select(KnowledgeTypeConfig).where(
        KnowledgeTypeConfig.knowledge_type == knowledge_type,
        KnowledgeTypeConfig.active.is_(True),
    )
    return db.execute(stmt).scalar_one_or_none()
