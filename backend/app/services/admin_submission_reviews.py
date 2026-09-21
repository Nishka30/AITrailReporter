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
from app.schemas.geographic_context import NearestKnownPlace
from app.schemas.submission import SubmissionAudioRead, SubmissionPhotoRead
from app.schemas.submission_review import SubmissionReviewRead
from app.schemas.transcription import TranscriptionRead
from app.services import geographic_context as geographic_context_service
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


def _resolve_question_text_and_confirmed_place(
    db: Session, submission: Submission
) -> tuple[str | None, UUID | None, str | None]:
    """(question_text, location_id, location_name) for a submission that
    answers a question -- both CONFIRMED, not approximated: a place-question
    answer's location_id is the exact place it was about, via a plain FK
    lookup (no PostGIS, no radius, no distance -- there is nothing
    approximate about it). Runs unconditionally, including in the paginated
    list, because it costs one cheap get()-by-primary-key at most, only when
    the submission actually answers a question.

    Deliberately split out from the nearest-known-place FALLBACK below (see
    _attach_nearest_known_place): that one is real enrichment-only PostGIS
    work and must never run per-row in a list.
    """
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


def _submissions_needing_nearest_place(
    rows: list[tuple[SubmissionReview, Submission, Guide]],
) -> dict[UUID, tuple[float, float]]:
    """Which of a PAGE's submissions are even candidates for the nearest-
    known-place enrichment: free-form contributions (no confirmed place of
    their own) with a real coordinate. Used to build ONE batched query's
    input -- see geographic_context.batch_nearest_known_places -- rather
    than one PostGIS query per row.
    """
    points: dict[UUID, tuple[float, float]] = {}
    for _review, submission, _guide in rows:
        if submission.source_place_question_id is not None:
            continue  # already has a CONFIRMED place, no lookup needed
        if submission.latitude is not None and submission.longitude is not None:
            points[submission.id] = (float(submission.latitude), float(submission.longitude))
    return points


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


def _to_item(
    db: Session,
    review: SubmissionReview,
    submission: Submission,
    guide: Guide,
    *,
    nearest_place: NearestKnownPlace | None = None,
) -> ContributionQueueItem:
    """`latitude`/`longitude`/`location_label`/`external_place_id` are always
    populated here at zero extra query cost -- they are plain columns on
    `submission`, the contribution's OWN authoritative location.

    `nearest_place` is real, optional PostGIS enrichment -- "is a known
    Location nearby" -- ALREADY RESOLVED by the caller (batched for a whole
    page via geographic_context.batch_nearest_known_places, or single-row
    for a detail read via resolve_geographic_context). This function never
    queries for it itself, so it costs nothing extra to call per row.
    """
    question_text, confirmed_location_id, confirmed_location_name = (
        _resolve_question_text_and_confirmed_place(db, submission)
    )
    if confirmed_location_id is not None:
        location_id, location_name, location_distance_meters = (
            confirmed_location_id, confirmed_location_name, None,
        )
    elif nearest_place is not None:
        location_id, location_name, location_distance_meters = (
            nearest_place.id, nearest_place.name, nearest_place.distance_meters,
        )
    else:
        location_id, location_name, location_distance_meters = None, None, None
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
        location_label=submission.location_label,
        external_place_id=submission.external_place_id,
        location_id=location_id,
        location_name=location_name,
        location_distance_meters=location_distance_meters,
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
    # ONE batched PostGIS query for the whole page (see
    # geographic_context.batch_nearest_known_places), not one per row --
    # this is what lets the list show a "Near <place>" caption without
    # reintroducing the N+1 pattern that was deliberately removed.
    nearest_places = geographic_context_service.batch_nearest_known_places(
        db, _submissions_needing_nearest_place(rows)
    )
    items = [
        _to_item(db, review, submission, guide, nearest_place=nearest_places.get(submission.id))
        for review, submission, guide in rows
    ]
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

    nearest_place = None
    if submission.source_place_question_id is None and submission.latitude is not None and submission.longitude is not None:
        context = geographic_context_service.resolve_geographic_context(
            db, float(submission.latitude), float(submission.longitude)
        )
        nearest_place = context.nearest_known_place
    item = _to_item(db, review, submission, guide, nearest_place=nearest_place)

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
