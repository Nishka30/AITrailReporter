from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

SubmissionReviewStatus = Literal["pending_review", "approved", "rejected"]
# Identical vocabulary to observation_moderation's RejectionReason on purpose
# -- see app/db/models/submission_review.py's module docstring for why these
# are two independent tables reviewing different things, sharing one closed
# set of reasons (and, in the admin app, one reusable picker component).
RejectionReason = Literal["inaccurate", "unsafe", "duplicate", "poor_quality", "not_useful", "other"]


class SubmissionReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    submission_id: UUID
    guide_id: UUID
    status: SubmissionReviewStatus
    decided_by: str | None
    decided_at: datetime | None
    rejection_reason: RejectionReason | None
    rejection_note: str | None
    # What this contribution is queued to pay (or did pay) -- resolved once,
    # at submission time, and frozen here; see the model's docstring for why
    # approval replays this exact key rather than re-resolving it later.
    reward_rule_key: str
    # Only set once approved (see submission_review.approve). None while
    # pending or rejected -- 0 would be ambiguous with "the rule was worth
    # zero points", so "not decided yet" is represented as None instead.
    reward_points_awarded: int | None
    created_at: datetime
    updated_at: datetime


class RejectSubmissionRequest(BaseModel):
    reason: RejectionReason
    note: str | None = Field(default=None, max_length=2000)


class GuideSubmissionReviewRead(BaseModel):
    """One entry in a guide's own contribution-review status list (GET
    /guides/{guide_id}/submission-reviews) -- what the mobile app polls to
    learn whether a specific contribution it already knows about locally
    (identified by client_submission_id, the same id it generated and
    already stores) has moved from pending to approved/rejected.

    Deliberately thinner than the admin-facing SubmissionReviewRead: no
    internal reward_rule_key/idempotency_key/reward_source_* -- a guide's own
    device has no use for those, only for the decision and, if approved, the
    points.
    """

    submission_id: UUID
    # The id the mobile app itself generated at submission time -- this is
    # the join key back to its local LocalCapture/LocalAnswer row. Always
    # present: every row here came from a call site that requires one.
    client_submission_id: str
    submission_type: str
    status: SubmissionReviewStatus
    rejection_reason: RejectionReason | None
    rejection_note: str | None
    decided_at: datetime | None
    # Present only once status == 'approved'. The app must not display a
    # reward as earned while this is None.
    reward_points_awarded: int | None
    updated_at: datetime
