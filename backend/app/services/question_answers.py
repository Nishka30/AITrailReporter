"""Guide answer workflow (Step 13): persists a guide's answer to an assigned
Question, marks the QuestionAssignment 'completed', and makes the answer
available to the EXISTING extraction pipeline by representing it as a
Submission -- reusing app/services/extractions.py, app/services/source_text.py,
and app/services/observations.py entirely unmodified. No LLM call happens in
this module; extraction remains a separate, explicit action (POST
.../submissions/{id}/extract), exactly as it already is for notes and voice
submissions -- this step does not change when/how extraction is triggered.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.question import Question
from app.db.models.question_answer import QuestionAnswer
from app.db.models.question_assignment import QuestionAssignment
from app.db.models.submission import Submission


class QuestionNotFoundError(Exception):
    def __init__(self, question_id: UUID):
        self.question_id = question_id
        super().__init__(f"Question {question_id} not found")


class NoActiveAssignmentError(Exception):
    """Raised when a question has no assignment at all to answer -- either it
    was never assigned (Step 12's documented 'no guide available' case), or
    (in a future step) every assignment was retracted."""

    def __init__(self, question_id: UUID):
        self.question_id = question_id
        super().__init__(f"Question {question_id} is not currently assigned to any guide")


class AssignmentOwnershipError(Exception):
    """Raised when the answering guide_id does not match the CURRENT
    assignment's guide_id -- this question was not assigned to them."""

    def __init__(self, assignment: QuestionAssignment):
        self.assignment = assignment
        super().__init__("This question is not assigned to the given guide")


class AssignmentCancelledError(Exception):
    """Raised when the current assignment's status is 'cancelled'. Preserves
    Step 12's existing semantics (cancellation functionality itself is not
    implemented in this step) -- an assignment that somehow reaches
    'cancelled' is simply not answerable."""

    def __init__(self, assignment: QuestionAssignment):
        self.assignment = assignment
        super().__init__("This question's assignment was cancelled")


class AlreadyAnsweredError(Exception):
    """Raised when the current assignment is already 'completed' and this is
    a genuinely NEW answer attempt (a different client_answer_id) -- one
    guide answer must not silently overwrite another. A retry using the SAME
    client_answer_id that produced the completed state is handled as an
    idempotent replay instead and never reaches this branch."""

    def __init__(self, assignment: QuestionAssignment):
        self.assignment = assignment
        super().__init__("This question has already been answered")


class AnswerConflictError(Exception):
    """Raised when a client_answer_id is reused with a different
    question_id/guide_id/answer_text than the original request it was first
    used for."""

    def __init__(self, existing: QuestionAnswer):
        self.existing = existing
        super().__init__(
            f"client_answer_id {existing.client_answer_id!r} was already used "
            "with different answer data"
        )


def get_answer(db: Session, answer_id: UUID) -> QuestionAnswer | None:
    return db.get(QuestionAnswer, answer_id)


def get_answer_by_client_id(db: Session, client_answer_id: str) -> QuestionAnswer | None:
    stmt = select(QuestionAnswer).where(QuestionAnswer.client_answer_id == client_answer_id)
    return db.execute(stmt).scalar_one_or_none()


def get_latest_answer_for_question(db: Session, question_id: UUID) -> QuestionAnswer | None:
    """Most recent answer for a question, if any -- this step only ever
    creates at most one per question (the assignment lock in submit_answer
    below prevents a second one), but reads defensively in case a future
    reassignment/re-answer step changes that."""
    stmt = (
        select(QuestionAnswer)
        .where(QuestionAnswer.question_id == question_id)
        .order_by(QuestionAnswer.answered_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def _ensure_compatible(
    existing: QuestionAnswer, question_id: UUID, guide_id: UUID, answer_text: str
) -> None:
    if (
        existing.question_id != question_id
        or existing.guide_id != guide_id
        or existing.answer_text != answer_text
    ):
        raise AnswerConflictError(existing)


def submit_answer(
    db: Session,
    question_id: UUID,
    guide_id: UUID,
    client_answer_id: str,
    answer_text: str,
    answered_at: datetime,
) -> tuple[QuestionAnswer, bool]:
    """Persists a guide's answer to an assigned question. Returns
    (answer, created) -- created is False for an idempotent replay of an
    already-persisted answer.

    Raises QuestionNotFoundError, NoActiveAssignmentError,
    AssignmentOwnershipError, AssignmentCancelledError, AlreadyAnsweredError,
    or AnswerConflictError -- see each exception's docstring.

    Concurrency: the CURRENT QuestionAssignment row is locked (SELECT ... FOR
    UPDATE) for the duration of this function, the same "serialize on the
    thing being mutated" pattern as
    submissions.py:attach_audio_to_submission -- two concurrent answer
    attempts for the SAME assignment are fully serialized, so only the first
    to acquire the lock can transition it to 'completed'; every other
    concurrent caller observes 'completed' already set (AlreadyAnsweredError)
    or, if it's a replay of the SAME client_answer_id, is resolved by the
    IntegrityError-catch-and-refetch path below once the winner's row is
    visible. This does not hold the lock across any external call -- there is
    none here, unlike question generation's LLM call.
    """
    existing = get_answer_by_client_id(db, client_answer_id)
    if existing is not None:
        _ensure_compatible(existing, question_id, guide_id, answer_text)
        return existing, False

    question = db.get(Question, question_id)
    if question is None:
        raise QuestionNotFoundError(question_id)

    stmt = (
        select(QuestionAssignment)
        .where(QuestionAssignment.question_id == question_id)
        .order_by(QuestionAssignment.assigned_at.desc())
        .limit(1)
        .with_for_update()
    )
    assignment = db.execute(stmt).scalar_one_or_none()
    if assignment is None:
        db.commit()  # releases nothing (no lock was taken), but stays consistent with the pattern below
        raise NoActiveAssignmentError(question_id)
    if assignment.guide_id != guide_id:
        db.commit()
        raise AssignmentOwnershipError(assignment)
    if assignment.status == "cancelled":
        db.commit()
        raise AssignmentCancelledError(assignment)
    if assignment.status == "completed":
        db.commit()
        raise AlreadyAnsweredError(assignment)

    # Part F: the answer's geographic context is the QUESTION's own snapshotted
    # target coordinates (where the underlying knowledge gap actually is / was
    # observed to be stale) -- not the guide's current GPS position, which may
    # be wherever they happen to be typing from, possibly hours after the
    # event the answer describes. Setting these directly on the Submission
    # means extractions.py's existing _resolve_observation_coordinates picks
    # them up via its "submission already has latitude/longitude" branch
    # without any change to that function.
    submission = Submission(
        guide_id=guide_id,
        # Reuses client_answer_id as client_submission_id rather than minting a
        # second id: unlike a note+its separately-uploaded audio (two distinct
        # client actions), an answer and "the submission it produces" are the
        # SAME guide action from the client's perspective -- one id is enough,
        # and doing so lets the IntegrityError race path below double as this
        # function's own idempotent-replay recovery (see comment there).
        client_submission_id=client_answer_id,
        submission_type="answer",
        raw_text=answer_text,
        latitude=question.target_latitude,
        longitude=question.target_longitude,
        submitted_at=answered_at,
        status="received",
        source_question_id=question.id,
    )
    db.add(submission)
    try:
        db.flush()
    except IntegrityError:
        # Only reachable if a concurrent request for the SAME client_answer_id
        # raced this one and committed first while this transaction was
        # blocked on the assignment row lock above -- by the time we get here
        # the winner's QuestionAnswer row is already visible.
        db.rollback()
        existing = get_answer_by_client_id(db, client_answer_id)
        if existing is not None:
            _ensure_compatible(existing, question_id, guide_id, answer_text)
            return existing, False
        raise

    answer = QuestionAnswer(
        question_id=question_id,
        assignment_id=assignment.id,
        guide_id=guide_id,
        client_answer_id=client_answer_id,
        answer_text=answer_text,
        submission_id=submission.id,
        answered_at=answered_at,
    )
    db.add(answer)

    # Authoritative completion (Part C): only set here, after the answer and
    # its backing Submission have both been added in this same transaction --
    # never on the mere existence of locally-typed text on the mobile device.
    assignment.status = "completed"
    assignment.answered_at = answered_at

    db.commit()
    db.refresh(answer)
    return answer, True
