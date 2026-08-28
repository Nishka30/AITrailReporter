"""Contributors browser (Guides, from the admin's perspective). Treats
phone_number as sensitive: never joined into a list response casually, never
sent anywhere outside this authenticated admin API surface, never fed into
any LLM prompt.

Two aggregate queries computed ONCE for the whole list (not one query per
guide) to avoid an N+1 pattern and to avoid a fan-out join artifact: Submission
and Observation are both one-to-many from Guide but unrelated to each other,
so joining both in a single grouped query would multiply rows together and
inflate every count. Grouping each independently and combining the two
per-guide maps in Python avoids that without adding a query per guide.
"""

from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.db.models.guide import Guide
from app.db.models.observation import Observation
from app.db.models.observation_moderation import ObservationModeration
from app.db.models.submission import Submission
from app.schemas.admin import ContributorDetail, ContributorSummary
from app.services.admin_review import ReviewQueueFilters, list_review_queue


def _submission_stats(db: Session, guide_id: UUID | None = None) -> dict:
    stmt = select(
        Submission.guide_id,
        func.count(Submission.id),
        func.max(Submission.submitted_at),
    ).group_by(Submission.guide_id)
    if guide_id is not None:
        stmt = stmt.where(Submission.guide_id == guide_id)
    return {row[0]: (row[1], row[2]) for row in db.execute(stmt).all()}


def _observation_stats(db: Session, guide_id: UUID | None = None) -> dict:
    stmt = (
        select(
            Observation.guide_id,
            func.count(Observation.id),
            func.coalesce(func.sum(case((ObservationModeration.status == "approved", 1), else_=0)), 0),
            func.coalesce(func.sum(case((ObservationModeration.status == "rejected", 1), else_=0)), 0),
            func.coalesce(
                func.sum(case((ObservationModeration.status == "pending_review", 1), else_=0)), 0
            ),
        )
        .join(ObservationModeration, ObservationModeration.observation_id == Observation.id)
        .group_by(Observation.guide_id)
    )
    if guide_id is not None:
        stmt = stmt.where(Observation.guide_id == guide_id)
    return {row[0]: (row[1], row[2], row[3], row[4]) for row in db.execute(stmt).all()}


def _to_summary(guide: Guide, submission_stats: dict, observation_stats: dict) -> ContributorSummary:
    submission_count, last_active_at = submission_stats.get(guide.id, (0, None))
    observation_count, approved_count, rejected_count, pending_count = observation_stats.get(
        guide.id, (0, 0, 0, 0)
    )
    return ContributorSummary(
        guide_id=guide.id,
        name=guide.name,
        is_active=guide.is_active,
        submission_count=submission_count,
        observation_count=observation_count,
        approved_count=approved_count,
        rejected_count=rejected_count,
        pending_review_count=pending_count,
        last_active_at=last_active_at,
    )


def list_contributors(db: Session) -> list[ContributorSummary]:
    guides = db.execute(select(Guide).order_by(Guide.name)).scalars().all()
    submission_stats = _submission_stats(db)
    observation_stats = _observation_stats(db)
    return [_to_summary(guide, submission_stats, observation_stats) for guide in guides]


def get_contributor_detail(db: Session, guide_id: UUID, limit: int = 25) -> ContributorDetail | None:
    guide = db.get(Guide, guide_id)
    if guide is None:
        return None

    summary = _to_summary(guide, _submission_stats(db, guide_id), _observation_stats(db, guide_id))
    result = list_review_queue(db, ReviewQueueFilters(guide_id=guide_id), page=1, page_size=limit)

    return ContributorDetail(
        **summary.model_dump(),
        phone_number=guide.phone_number,
        recent_observations=result.items,
    )
