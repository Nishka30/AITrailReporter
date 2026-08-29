"""Answering a popular question (Step 18).

This is where the "secondary question source" rejoins the ONE knowledge
system. An answer here becomes an ordinary Submission and is handed to the
EXISTING pipeline -- app/services/extractions.py, source_text.py,
observations.py, observation_moderation.py -- all completely unmodified. There
is no second extraction path, no second observation type, and no second review
queue: the resulting observations land in the same admin moderation queue as
every other observation.

Deliberately simpler than question_answers.py, because a popular question has
no assignment to own or complete: it is not assigned to a specific guide, so
there is no ownership check, no 'completed' transition, and no
AlreadyAnsweredError -- several guides answering the same popular question is
legitimate and useful (more reports about the same place), not a conflict.
"""

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.location import Location
from app.db.models.place_question import PlaceQuestion
from app.db.models.submission import Submission
from app.services import extractions as extraction_service
from app.services import rewards as reward_service

logger = logging.getLogger(__name__)

# The generic fallback rate. The actual rule used is resolved per question from
# its contribution_kind -- see reward_service.place_question_rule_key.
REWARD_RULE_KEY = "place_question_answer"


class PlaceQuestionNotFoundError(Exception):
    def __init__(self, place_question_id: UUID):
        self.place_question_id = place_question_id
        super().__init__(f"Place question {place_question_id} not found")


class PlaceQuestionAnswerConflictError(Exception):
    """Raised when a client_answer_id is reused with different answer data --
    same contract as question_answers.AnswerConflictError."""

    def __init__(self, existing: Submission):
        self.existing = existing
        super().__init__(
            f"client_answer_id {existing.client_submission_id!r} was already used "
            "with different answer data"
        )


def _get_submission_by_client_id(db: Session, client_answer_id: str) -> Submission | None:
    stmt = select(Submission).where(Submission.client_submission_id == client_answer_id)
    return db.execute(stmt).scalar_one_or_none()


def submit_place_question_answer(
    db: Session,
    place_question_id: UUID,
    guide_id: UUID,
    client_answer_id: str,
    answer_text: str,
    answered_at: datetime,
) -> tuple[Submission, bool, int]:
    """Persists an answer to a popular question. Returns
    (submission, created, points_awarded).

    Idempotent on client_answer_id: a replayed sync returns the existing
    submission with created=False and points_awarded=0 -- the guide is paid
    once, on the first successful write, never again on a retry.

    The reward is written in the SAME transaction as the submission, so
    "the answer was stored" and "the guide was credited" are atomic. There is
    no path that credits points for an answer that wasn't saved, and none that
    saves an answer without crediting it.
    """
    existing = _get_submission_by_client_id(db, client_answer_id)
    if existing is not None:
        if (
            existing.guide_id != guide_id
            or existing.raw_text != answer_text
            or existing.source_place_question_id != place_question_id
        ):
            raise PlaceQuestionAnswerConflictError(existing)
        return existing, False, 0

    place_question = db.get(PlaceQuestion, place_question_id)
    if place_question is None:
        raise PlaceQuestionNotFoundError(place_question_id)

    location = db.get(Location, place_question.location_id)

    submission = Submission(
        guide_id=guide_id,
        # Same reasoning as question_answers.py: an answer and the submission
        # it produces are ONE client action, so the client's answer id serves
        # as the submission's client id too -- and doubles as the reward's
        # idempotency key below.
        client_submission_id=client_answer_id,
        # 'answer' rather than 'explore': this answers a question the system
        # posed, which is exactly what that type means. It is created
        # server-side only (never ingested via POST /submissions), same as a
        # knowledge-gap answer -- see schemas/submission.py.
        submission_type="answer",
        raw_text=answer_text,
        # The PLACE's coordinates, not the guide's current GPS -- the question
        # is about this place, so that is where the resulting observation
        # belongs. extractions._resolve_observation_coordinates picks these up
        # via its existing "submission already has lat/lon" branch, needing no
        # change there.
        latitude=location.latitude if location is not None else None,
        longitude=location.longitude if location is not None else None,
        submitted_at=answered_at,
        status="received",
        source_place_question_id=place_question.id,
    )
    db.add(submission)

    try:
        db.flush()
    except IntegrityError:
        # A concurrent request for the SAME client_answer_id won the race.
        db.rollback()
        existing = _get_submission_by_client_id(db, client_answer_id)
        if existing is not None:
            if (
                existing.guide_id != guide_id
                or existing.raw_text != answer_text
                or existing.source_place_question_id != place_question_id
            ):
                raise PlaceQuestionAnswerConflictError(existing)
            return existing, False, 0
        raise

    points = reward_service.award(
        db,
        guide_id=guide_id,
        # Paid at the rate for THIS question's contribution kind, not one flat
        # place-question rate -- the kinds differ in effort. Falls back to the
        # generic rule when a kind has no rate of its own.
        rule_key=reward_service.place_question_rule_key(db, place_question.contribution_kind),
        idempotency_key=client_answer_id,
        source_type="place_question_answer",
        source_id=submission.id,
    )

    db.commit()
    db.refresh(submission)

    # Same automatic-extraction trigger every other text submission uses --
    # called AFTER commit, never raises (see extractions.py).
    extraction_service.maybe_trigger_extraction(db, submission.id)
    return submission, True, points
