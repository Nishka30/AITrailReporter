"""The Contribution Review queue: does a guide get PAID for one submission or
answer? Deliberately separate from app/services/admin_review.py (which
reviews Observations for knowledge accuracy/public visibility) -- see
app/db/models/submission_review.py for why these are two different reviews of
two different things, and app/api/routes/admin.py for how the routes stay
under the same /api/v1/admin/* namespace and require_admin boundary.

Reuses the SAME audio/photo streaming routes admin_review's detail view uses
(GET /admin/submissions/{id}/audio|photo) -- no new media-serving code.
"""

from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models.guide import Guide
from app.db.models.location import Location
from app.db.models.place_question import PlaceQuestion
from app.db.models.question import Question
from app.db.models.submission import Submission
from app.db.models.submission_review import SubmissionReview
from app.db.models.transcription import Transcription
from app.db.models.reward import RewardRule
from app.schemas.admin import (
    ContributionDetail,
    ContributionQueueItem,
    ContributionQueueResult,
    RewardBreakdownLine,
)
from app.schemas.submission import SubmissionAudioRead, SubmissionPhotoRead
from app.schemas.submission_review import SubmissionReviewRead
from app.schemas.transcription import TranscriptionRead
from app.services import rewards as reward_service


class ContributionQueueFilters:
    def __init__(
        self,
        status: str | None = "pending_review",
        guide_id: UUID | None = None,
        submission_type: str | None = None,
        q: str | None = None,
    ):
        self.status = status
        self.guide_id = guide_id
        self.submission_type = submission_type
        self.q = q


def _base_query(filters: ContributionQueueFilters) -> Select:
    stmt = (
        select(SubmissionReview, Submission, Guide)
        .join(Submission, Submission.id == SubmissionReview.submission_id)
        .join(Guide, Guide.id == SubmissionReview.guide_id)
    )
    if filters.status is not None:
        stmt = stmt.where(SubmissionReview.status == filters.status)
    if filters.guide_id is not None:
        stmt = stmt.where(SubmissionReview.guide_id == filters.guide_id)
    if filters.submission_type is not None:
        stmt = stmt.where(Submission.submission_type == filters.submission_type)
    if filters.q:
        stmt = stmt.where(Submission.raw_text.ilike(f"%{filters.q}%"))
    return stmt


def _resolve_question_and_place(
    db: Session, submission: Submission
) -> tuple[str | None, UUID | None, str | None]:
    """(question_text, location_id, location_name) for the thing this
    submission answers, if it answers anything. A free-form Explore/memory
    contribution has none of these -- all three come back None, honestly,
    rather than a guessed nearest place."""
    if submission.source_place_question_id is not None:
        place_question = db.get(PlaceQuestion, submission.source_place_question_id)
        if place_question is not None:
            location = db.get(Location, place_question.location_id)
            return (
                place_question.question_text,
                place_question.location_id,
                location.name if location is not None else None,
            )
    if submission.source_question_id is not None:
        question = db.get(Question, submission.source_question_id)
        if question is not None:
            return question.question_text, None, None
    return None, None, None


def _rule_label(rule: RewardRule, fallback: str) -> str:
    return rule.description or fallback


# Rule key for the Explore/memory media bonus -- kept as a local constant
# (same value as submission_review._MEDIA_BONUS_RULE_KEY) since this module
# only needs it for display, not to award anything.
_MEDIA_BONUS_RULE_KEY = "explore_contribution_media_bonus"


def _reward_breakdown(
    db: Session, submission: Submission, rule_key: str
) -> tuple[list[RewardBreakdownLine], int]:
    """What this contribution is worth right now: the base rule plus any
    eligible media bonus, both resolved live from reward_rules. Mirrors
    submission_review.award_media_bonus's eligibility check EXACTLY (same
    submission_type/source_place_question_id/client_audio_id/client_photo_id
    conditions) so this display can never claim a bonus approve() wouldn't
    actually pay."""
    lines: list[RewardBreakdownLine] = []
    total = 0

    base_rule = reward_service.get_rule(db, rule_key)
    if base_rule is not None:
        lines.append(RewardBreakdownLine(label=_rule_label(base_rule, "Base contribution"), points=base_rule.points))
        total += base_rule.points

    media_eligible = (
        submission.submission_type in ("explore", "memory")
        and submission.source_place_question_id is None
        and (submission.client_audio_id is not None or submission.client_photo_id is not None)
    )
    if media_eligible:
        bonus_rule = reward_service.get_rule(db, _MEDIA_BONUS_RULE_KEY)
        if bonus_rule is not None:
            lines.append(RewardBreakdownLine(label=_rule_label(bonus_rule, "Photo/voice bonus"), points=bonus_rule.points))
            total += bonus_rule.points

    return lines, total


def _to_item(db: Session, review: SubmissionReview, submission: Submission, guide: Guide) -> ContributionQueueItem:
    question_text, location_id, location_name = _resolve_question_and_place(db, submission)
    breakdown, total_points = _reward_breakdown(db, submission, review.reward_rule_key)
    return ContributionQueueItem(
        submission_id=submission.id,
        submission_type=submission.submission_type,
        guide_id=guide.id,
        guide_name=guide.name,
        raw_text=submission.raw_text,
        submitted_at=submission.submitted_at,
        latitude=float(submission.latitude) if submission.latitude is not None else None,
        longitude=float(submission.longitude) if submission.longitude is not None else None,
        location_id=location_id,
        location_name=location_name,
        question_text=question_text,
        has_audio=submission.audio is not None,
        has_photo=submission.photo is not None,
        review=SubmissionReviewRead.model_validate(review),
        current_rule_points=total_points,
        reward_breakdown=breakdown,
    )


def list_contribution_queue(
    db: Session, filters: ContributionQueueFilters, page: int, page_size: int
) -> ContributionQueueResult:
    stmt = _base_query(filters)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    stmt = stmt.order_by(SubmissionReview.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    rows = db.execute(stmt).all()
    items = [_to_item(db, review, submission, guide) for review, submission, guide in rows]
    return ContributionQueueResult(items=items, total=total, page=page, page_size=page_size)


def get_contribution_detail(db: Session, submission_id: UUID) -> ContributionDetail | None:
    stmt = (
        select(SubmissionReview, Submission, Guide)
        .join(Submission, Submission.id == SubmissionReview.submission_id)
        .join(Guide, Guide.id == SubmissionReview.guide_id)
        .where(SubmissionReview.submission_id == submission_id)
    )
    row = db.execute(stmt).first()
    if row is None:
        return None
    review, submission, guide = row

    item = _to_item(db, review, submission, guide)

    transcript = None
    if submission.audio is not None:
        transcription_row = db.execute(
            select(Transcription).where(Transcription.submission_id == submission.id)
        ).scalar_one_or_none()
        if transcription_row is not None:
            transcript = TranscriptionRead.model_validate(transcription_row)

    return ContributionDetail(
        item=item,
        audio=SubmissionAudioRead.model_validate(submission.audio) if submission.audio else None,
        photo=SubmissionPhotoRead.model_validate(submission.photo) if submission.photo else None,
        transcript=transcript,
        guide_phone_number=guide.phone_number,
    )


def counts_by_status(db: Session) -> dict[str, int]:
    """One COUNT() query, grouped by status -- feeds AdminOverview's
    contribution_* fields without three separate round trips."""
    rows = db.execute(
        select(SubmissionReview.status, func.count()).group_by(SubmissionReview.status)
    ).all()
    counts = {status: count for status, count in rows}
    return {
        "pending_review": counts.get("pending_review", 0),
        "approved": counts.get("approved", 0),
        "rejected": counts.get("rejected", 0),
    }
