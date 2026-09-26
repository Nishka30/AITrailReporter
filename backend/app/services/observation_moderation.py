"""Core lifecycle for the admin content-moderation layer: does ONE Observation
get to eventually be visible to a future public app? See
app/db/models/observation_moderation.py for why this is a separate table
rather than columns on Observation.

Nothing here duplicates the Observation/Extraction/Submission pipeline --
this module only ever reads an observation_id that already exists and manages
a 1:1 moderation row alongside it.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.location import Location
from app.db.models.observation import Observation
from app.db.models.observation_moderation import (
    REJECTION_REASONS,
    ObservationModeration,
)
from app.db.models.submission import Submission
from app.services import category_knowledge as category_knowledge_service
from app.services import knowledge_relation as knowledge_relation_service


class ModerationNotFoundError(Exception):
    """Raised when no moderation row exists for the given observation_id --
    should not happen for any observation created after this feature shipped
    (see ensure_pending_moderation, called atomically at extraction time), but
    is possible for data from before the backfill migration ran, or if the
    caller passes a bad id."""

    def __init__(self, observation_id: UUID):
        self.observation_id = observation_id
        super().__init__(f"No moderation record exists for observation {observation_id}")


class AlreadyDecidedError(Exception):
    """Raised by approve()/reject() when the observation has already been
    decided the OTHER way. Approving an already-approved (or rejecting an
    already-rejected) observation is treated as an idempotent no-op instead --
    see approve()/reject() below -- but switching the decision itself requires
    the explicit change_decision() action, not a second call to approve/reject."""

    def __init__(self, moderation: ObservationModeration):
        self.moderation = moderation
        super().__init__(
            f"Observation {moderation.observation_id} was already decided "
            f"({moderation.status}); use change_decision to switch it"
        )


class NotYetDecidedError(Exception):
    """Raised by change_decision() when the observation is still
    pending_review -- there is no prior decision to change; use approve()/
    reject() to make the first decision."""

    def __init__(self, moderation: ObservationModeration):
        self.moderation = moderation
        super().__init__(
            f"Observation {moderation.observation_id} has not been decided yet "
            "(pending_review) -- use approve/reject, not change_decision"
        )


def get_moderation(db: Session, observation_id: UUID) -> ObservationModeration | None:
    stmt = select(ObservationModeration).where(
        ObservationModeration.observation_id == observation_id
    )
    return db.execute(stmt).scalar_one_or_none()


def ensure_pending_moderation(db: Session, observation_id: UUID) -> ObservationModeration:
    """Get-or-create a 'pending_review' row for an observation that was just
    inserted. INSERT-race pattern (IntegrityError-catch-and-refetch), not
    SELECT ... FOR UPDATE, because -- same reasoning as
    extractions.py::_get_or_create_extraction_row -- there is nothing to lock
    the first time this observation's moderation row is created.

    Called from app/services/extractions.py in the SAME transaction as the
    Observation insert, so there is never a window where an Observation exists
    with no moderation row."""
    existing = get_moderation(db, observation_id)
    if existing is not None:
        return existing

    moderation = ObservationModeration(observation_id=observation_id, status="pending_review")
    db.add(moderation)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = get_moderation(db, observation_id)
        if existing is None:
            raise
        return existing
    return moderation


def _answer_text_from_observation(observation: Observation) -> str:
    """The guide's raw answer text this Observation carries -- see
    extractions.py::extract_category_knowledge_observation, which always
    stores it as value={"answer_text": ...} for a category-knowledge
    Observation. Falls back to `evidence` (also set to the same text there)
    so this never breaks on a shape this function doesn't expect."""
    value = observation.value
    if isinstance(value, dict):
        text = value.get("answer_text")
        if isinstance(text, str) and text.strip():
            return text.strip()
    return (observation.evidence or "").strip()


def _source_question_id_for(db: Session, observation: Observation) -> UUID | None:
    """The PlaceQuestion this Observation's answer was submitted against, if
    any -- Observation itself carries no such column (see its model
    docstring: it is the SHARED ledger for both knowledge systems), so this
    is resolved one hop out via the originating Submission, exactly the way
    place_question_answers.py already links the two."""
    submission = db.get(Submission, observation.submission_id)
    return submission.source_place_question_id if submission is not None else None


def _maybe_verify_category_knowledge(db: Session, observation_id: UUID, decided_at: datetime) -> None:
    """THE single call site that ever mutates CategoryKnowledge trust state
    (last_verified_at, or a supersession) -- fires only when the Observation
    being approved is category-knowledge evidence (category_knowledge_id
    set), which is exactly the PRIMARY system's definition of "a trusted
    guide verified this." A hazard Observation (category_knowledge_id NULL)
    is a no-op here.

    TWO CASES, per the architecture hardening directive's Part 2:

    1. The targeted CategoryKnowledge row has never been verified before
       (last_verified_at is NULL) -- this IS the first verification, and its
       own knowledge_text already came directly from this same answer (see
       extractions.py's first-ask branch). Nothing to compare against yet:
       just mark_verified.

    2. The row was already verified once -- this new, approved Observation
       is necessarily a RE-verification of standing knowledge, and its
       relationship to that knowledge must be classified before anything is
       mutated (see knowledge_relation.classify_relation): CONFIRMS refreshes
       the same row, CONTRADICTS supersedes it (full history preserved),
       UNCERTAIN mutates nothing and opens an explicit admin-resolvable
       conflict instead (category_knowledge.record_conflict). Never a naive
       string-equality check -- see knowledge_relation.py's module docstring
       for why.
    """
    observation = db.get(Observation, observation_id)
    if observation is None or observation.category_knowledge_id is None:
        return

    item = category_knowledge_service.get_knowledge_item(db, observation.category_knowledge_id)
    if item is None:
        return

    if item.last_verified_at is None:
        category_knowledge_service.mark_verified(db, item.id, decided_at)
        return

    new_answer_text = _answer_text_from_observation(observation)
    if not new_answer_text:
        # Nothing to classify a relationship from -- leave standing knowledge
        # untouched and flag it rather than silently doing nothing at all.
        category_knowledge_service.record_conflict(
            db,
            category_knowledge_id=item.id,
            observation_id=observation.id,
            new_answer_text=new_answer_text,
        )
        return

    location = db.get(Location, item.location_id)
    labels = category_knowledge_service.get_category_labels_for_assignments(
        db, [item.category_assignment_id]
    )
    _slug, category_display_name = labels.get(item.category_assignment_id, ("", "this category"))
    place_name = location.name if location is not None else "this place"

    result = knowledge_relation_service.classify_relation(
        item.knowledge_text, new_answer_text, category_display_name, place_name
    )

    if result.relation == knowledge_relation_service.RELATION_CONFIRMS:
        category_knowledge_service.mark_verified(db, item.id, decided_at)
    elif result.relation == knowledge_relation_service.RELATION_CONTRADICTS:
        source_question_id = _source_question_id_for(db, observation)
        category_knowledge_service.supersede_knowledge_item(
            db,
            old_item=item,
            new_knowledge_text=result.new_knowledge_text,
            volatility=item.volatility,
            source_question_id=source_question_id,
            verified_at=decided_at,
        )
    else:
        category_knowledge_service.record_conflict(
            db,
            category_knowledge_id=item.id,
            observation_id=observation.id,
            new_answer_text=new_answer_text,
        )


def _lock_moderation(db: Session, observation_id: UUID) -> ObservationModeration:
    stmt = (
        select(ObservationModeration)
        .where(ObservationModeration.observation_id == observation_id)
        .with_for_update()
    )
    moderation = db.execute(stmt).scalar_one_or_none()
    if moderation is None:
        raise ModerationNotFoundError(observation_id)
    return moderation


def approve(db: Session, observation_id: UUID, decided_by: str) -> ObservationModeration:
    """Approves an observation for eventual public visibility. Only valid from
    'pending_review' -- re-approving an already-approved observation is a
    harmless idempotent no-op (e.g. a retried request), but an already-
    REJECTED observation raises AlreadyDecidedError: switching a prior
    decision is a deliberate, separate action (see change_decision), not
    something this endpoint does silently.

    Concurrency: the moderation row is locked (SELECT ... FOR UPDATE) for the
    duration of this call, the same pattern used throughout this codebase
    (e.g. attach_audio_to_submission) -- two concurrent decisions on the same
    observation are fully serialized."""
    moderation = _lock_moderation(db, observation_id)

    if moderation.status == "approved":
        db.commit()
        return moderation
    if moderation.status == "rejected":
        db.commit()
        raise AlreadyDecidedError(moderation)

    moderation.status = "approved"
    moderation.decided_by = decided_by
    moderation.decided_at = datetime.now(timezone.utc)
    moderation.rejection_reason = None
    moderation.rejection_note = None
    _maybe_verify_category_knowledge(db, observation_id, moderation.decided_at)
    db.commit()
    db.refresh(moderation)
    return moderation


def reject(
    db: Session, observation_id: UUID, decided_by: str, reason: str, note: str | None
) -> ObservationModeration:
    """Rejects an observation. Preserves the source Submission/Observation
    untouched and unremoved -- rejection only ever records a decision
    alongside the evidence, never deletes it. Same 'pending_review'-only
    precondition and idempotent-no-op-on-repeat behavior as approve() above,
    mirrored exactly."""
    if reason not in REJECTION_REASONS:
        raise ValueError(f"Unknown rejection reason: {reason!r}")

    moderation = _lock_moderation(db, observation_id)

    if moderation.status == "rejected":
        db.commit()
        return moderation
    if moderation.status == "approved":
        db.commit()
        raise AlreadyDecidedError(moderation)

    moderation.status = "rejected"
    moderation.decided_by = decided_by
    moderation.decided_at = datetime.now(timezone.utc)
    moderation.rejection_reason = reason
    moderation.rejection_note = note
    db.commit()
    db.refresh(moderation)
    return moderation


def change_decision(
    db: Session,
    observation_id: UUID,
    decided_by: str,
    new_status: str,
    reason: str | None,
    note: str | None,
) -> ObservationModeration:
    """Explicitly switches an ALREADY-DECIDED observation to the opposite
    decision (approved <-> rejected). Raises NotYetDecidedError if the
    observation is still pending_review -- there is nothing to change yet;
    use approve()/reject() for the first decision instead.

    This is a deliberately separate action from approve()/reject() per
    product decision: an admin reversing a previous call is a distinct,
    accountable event (its own decided_by/decided_at), not something that
    happens implicitly by clicking the same approve/reject button twice."""
    if new_status == "rejected" and reason not in REJECTION_REASONS:
        raise ValueError(f"Unknown rejection reason: {reason!r}")

    moderation = _lock_moderation(db, observation_id)

    if moderation.status == "pending_review":
        db.commit()
        raise NotYetDecidedError(moderation)

    moderation.status = new_status
    moderation.decided_by = decided_by
    moderation.decided_at = datetime.now(timezone.utc)
    if new_status == "approved":
        moderation.rejection_reason = None
        moderation.rejection_note = None
        _maybe_verify_category_knowledge(db, observation_id, moderation.decided_at)
    else:
        moderation.rejection_reason = reason
        moderation.rejection_note = note
    db.commit()
    db.refresh(moderation)
    return moderation
