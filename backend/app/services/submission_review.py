"""Whether a Submission/answer gets PAID: the admin-approval gate on rewards.

Structurally mirrors app/services/observation_moderation.py (same
get-or-create-then-lock-then-decide shape) because it is solving the same
KIND of problem -- a human decision that gates something -- but it gates
`reward_service.award()`, not public visibility. See
app/db/models/submission_review.py for why this is a separate table/lifecycle
from ObservationModeration rather than a reuse of it.

Nothing here duplicates the reward system: `approve()` calls the SAME
`reward_service.award()` used everywhere else, with the SAME idempotency_key
that would have been used at submission time before this feature existed. The
only thing that changed is WHEN that call happens.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.submission import Submission
from app.db.models.submission_review import REJECTION_REASONS, SubmissionReview
from app.services import rewards as reward_service

# Rule key for the Explore/memory media bonus (see award_media_bonus below).
# Lives here, not in submissions.py, because gating it is this module's job.
_MEDIA_BONUS_RULE_KEY = "explore_contribution_media_bonus"


class SubmissionReviewNotFoundError(Exception):
    """Raised when no review row exists for the given submission_id -- should
    not happen for any reward-eligible submission created after this feature
    shipped (ensure_pending_review is called in the same transaction as the
    submission/answer insert), but is possible for a submission that predates
    this feature (never gated, already paid under the old immediate-award
    behavior) or a caller-supplied bad id."""

    def __init__(self, submission_id: UUID):
        self.submission_id = submission_id
        super().__init__(f"No review record exists for submission {submission_id}")


class AlreadyDecidedError(Exception):
    """Raised by approve()/reject() when the submission has already been
    decided the OTHER way. Re-approving an already-approved (or re-rejecting
    an already-rejected) submission is an idempotent no-op instead -- see
    approve()/reject() below. There is deliberately no change_decision() here
    the way ObservationModeration has one: once a reward has been paid there
    is no clawback mechanism anywhere in this codebase, so 'approved ->
    rejected' would be dishonest (the points stay paid regardless), and
    'rejected -> approved' would create a reward for an action an admin
    already told the guide would not be paid. Both directions are refused
    rather than silently doing something the ledger can't actually represent.
    """

    def __init__(self, review: SubmissionReview):
        self.review = review
        super().__init__(
            f"Submission {review.submission_id} was already decided ({review.status})"
        )


def get_review(db: Session, submission_id: UUID) -> SubmissionReview | None:
    stmt = select(SubmissionReview).where(SubmissionReview.submission_id == submission_id)
    return db.execute(stmt).scalar_one_or_none()


def list_for_guide(
    db: Session, guide_id: UUID, *, since: datetime | None = None, limit: int = 200
) -> list[tuple[SubmissionReview, Submission]]:
    """A guide's own contribution-review rows, most recently updated first --
    what the mobile app polls (GET /guides/{guide_id}/submission-reviews) to
    learn whether a locally-known contribution has been decided since it last
    checked. `since` (typically the last successful poll's newest
    `updated_at`) narrows this to what actually changed, so a guide with a
    long history doesn't re-fetch everything every time -- purely an
    optimization, the mobile app still keys matches on client_submission_id,
    never on ordering or count.
    """
    stmt = (
        select(SubmissionReview, Submission)
        .join(Submission, Submission.id == SubmissionReview.submission_id)
        .where(SubmissionReview.guide_id == guide_id)
    )
    if since is not None:
        stmt = stmt.where(SubmissionReview.updated_at > since)
    stmt = stmt.order_by(SubmissionReview.updated_at.desc()).limit(limit)
    return list(db.execute(stmt).all())


def ensure_pending_review(
    db: Session,
    *,
    submission_id: UUID,
    guide_id: UUID,
    reward_rule_key: str,
    reward_idempotency_key: str,
    reward_source_type: str,
    reward_source_id: UUID | None,
) -> SubmissionReview:
    """Get-or-create a 'pending_review' row for a just-inserted, reward-
    eligible submission/answer. Call this INSTEAD of reward_service.award() at
    submission time -- see the three call sites in submissions.py/
    question_answers.py/place_question_answers.py.

    INSERT-race pattern (IntegrityError-catch-and-refetch), not
    SELECT ... FOR UPDATE, matching
    observation_moderation.ensure_pending_moderation: there is nothing to lock
    the first time this submission's review row is created.

    Must be called in the SAME transaction as the Submission/answer insert
    (does not commit itself), so "the contribution was saved" and "it is
    queued for reward review" happen together or not at all -- identical
    contract to the reward_service.award() call this replaces.
    """
    existing = get_review(db, submission_id)
    if existing is not None:
        return existing

    review = SubmissionReview(
        submission_id=submission_id,
        guide_id=guide_id,
        status="pending_review",
        reward_rule_key=reward_rule_key,
        reward_idempotency_key=reward_idempotency_key,
        reward_source_type=reward_source_type,
        reward_source_id=reward_source_id,
    )
    db.add(review)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = get_review(db, submission_id)
        if existing is None:
            raise
        return existing
    return review


def _lock_review(db: Session, submission_id: UUID) -> SubmissionReview:
    stmt = (
        select(SubmissionReview)
        .where(SubmissionReview.submission_id == submission_id)
        .with_for_update()
    )
    review = db.execute(stmt).scalar_one_or_none()
    if review is None:
        raise SubmissionReviewNotFoundError(submission_id)
    return review


def approve(db: Session, submission_id: UUID, decided_by: str) -> tuple[SubmissionReview, int]:
    """Approves a contribution for payment, and pays it -- exactly once.

    Returns (review, points_awarded). `points_awarded` is 0 for an idempotent
    replay of an already-approved submission (a retried admin click, or two
    concurrent approve requests) -- the guide was already paid the first time.
    An already-REJECTED submission raises AlreadyDecidedError: there is no
    reversal path (see AlreadyDecidedError's docstring for why).

    Double-payment is impossible even if this function's own idempotency check
    below were somehow bypassed: reward_service.award() itself is guarded by
    the UNIQUE constraint on reward_ledger.idempotency_key, which is the same
    idempotency_key this row was created with. This function's own status
    check is what makes a *repeat approval request return the correct,
    truthful `points_awarded=0`* rather than relying solely on the ledger's
    silent no-op -- but even without it, no second ledger row could ever be
    written.

    Concurrency: the review row is locked (SELECT ... FOR UPDATE) for the
    duration of this call, the same pattern used throughout this codebase
    (e.g. observation_moderation.approve, attach_audio_to_submission) -- two
    concurrent approve requests for the same submission are fully serialized;
    the second to acquire the lock sees 'approved' already set and returns
    (review, 0) without calling award() again.
    """
    review = _lock_review(db, submission_id)

    if review.status == "approved":
        db.commit()
        return review, 0
    if review.status == "rejected":
        db.commit()
        raise AlreadyDecidedError(review)

    points = reward_service.award(
        db,
        guide_id=review.guide_id,
        rule_key=review.reward_rule_key,
        idempotency_key=review.reward_idempotency_key,
        source_type=review.reward_source_type,
        source_id=review.reward_source_id,
    )

    review.status = "approved"
    review.decided_by = decided_by
    review.decided_at = datetime.now(timezone.utc)
    review.reward_points_awarded = points

    # Pay the media bonus too, in this SAME decision, if a photo/voice note
    # was already attached by the time the admin approved -- see
    # award_media_bonus's docstring. No-op (returns 0) for a plain text
    # contribution or one with no media yet.
    submission = db.get(Submission, submission_id)
    bonus_points = award_media_bonus(db, submission, review) if submission is not None else 0

    db.commit()
    db.refresh(review)
    return review, points + bonus_points


def award_media_bonus(db: Session, submission: Submission, review: SubmissionReview) -> int:
    """Awards the Explore/memory media bonus for an APPROVED contribution, if
    it is eligible and has a photo or voice note attached. Returns the points
    actually awarded (0 if ineligible, no media yet, or already paid).

    This is the single place the media bonus is decided -- there is no
    separate/second reward system. It is called from two places:

    1. approve() below, for a submission whose media was already attached
       BEFORE the admin decision (the common case).
    2. submissions.py's attach_audio_to_submission/attach_photo_to_submission,
       for the rarer case where media arrives AFTER the submission was
       already approved -- the base contribution already cleared admin
       review, so enrichment media attached afterward does not need a second
       review cycle; it is paid the moment it exists. Those call sites only
       reach this function when `review.status == "approved"`; pending or
       rejected submissions withhold the bonus exactly like the base reward
       (see submissions.py::_maybe_award_media_bonus).

    Uses the SAME idempotency key (`{client_submission_id}:media`) and rule
    key that were used when this bonus was immediate/ungated, so a
    contribution's total paid points cannot double-count regardless of how
    many times media is attached or approval is retried.

    Adds the bonus onto `review.reward_points_awarded` (rather than a
    separate column) so that field always reflects the TOTAL actually paid
    for this contribution -- what mobile displays as "you earned X points".
    Does not commit; the caller commits.
    """
    if submission.submission_type not in ("explore", "memory") or submission.client_submission_id is None:
        return 0
    if submission.source_place_question_id is not None:
        return 0
    if submission.client_audio_id is None and submission.client_photo_id is None:
        return 0

    bonus_points = reward_service.award(
        db,
        guide_id=submission.guide_id,
        rule_key=_MEDIA_BONUS_RULE_KEY,
        idempotency_key=f"{submission.client_submission_id}:media",
        source_type=(
            "memory_submission" if submission.submission_type == "memory" else "explore_submission"
        ),
        source_id=submission.id,
    )
    if bonus_points:
        review.reward_points_awarded = (review.reward_points_awarded or 0) + bonus_points
    return bonus_points


def reject(
    db: Session, submission_id: UUID, decided_by: str, reason: str, note: str | None
) -> SubmissionReview:
    """Rejects a contribution. No reward is ever granted for a rejected
    submission -- award() is simply never called on this path, so there is
    nothing to undo later.

    Preserves the source Submission untouched -- rejection only ever records
    a decision alongside it, never deletes or alters the contribution itself.
    Same 'pending_review'-only precondition and idempotent-no-op-on-repeat
    behavior as approve() above, mirrored exactly (and for the same reason:
    already-approved means already paid, and there is no reversal path)."""
    if reason not in REJECTION_REASONS:
        raise ValueError(f"Unknown rejection reason: {reason!r}")

    review = _lock_review(db, submission_id)

    if review.status == "rejected":
        db.commit()
        return review
    if review.status == "approved":
        db.commit()
        raise AlreadyDecidedError(review)

    review.status = "rejected"
    review.decided_by = decided_by
    review.decided_at = datetime.now(timezone.utc)
    review.rejection_reason = reason
    review.rejection_note = note
    db.commit()
    db.refresh(review)
    return review
