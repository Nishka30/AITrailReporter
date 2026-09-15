"""add submission review (admin approval gate on rewards)

Revision ID: c8f4a1d9e356
Revises: 9b3f27c5a814
Create Date: 2026-09-15

Introduces the admin-approval gate between "a guide submitted/answered
something" and "the guide gets paid for it". Before this migration,
reward_service.award() was called synchronously at submission/answer time,
with no review step of any kind (see app/services/rewards.py's four existing
call sites). After this migration, those call sites create a
'pending_review' row here instead of calling award() directly; the actual
award() call moves to submission_review.approve(), in
app/services/submission_review.py, and fires exactly once (guarded by the
SAME reward_ledger.idempotency_key UNIQUE constraint that already protected
every other award() call site).

Deliberately a NEW, separate table from the existing observation_moderation
(which reviews EXTRACTED FACTS, zero-to-many per submission) rather than a
reuse of it -- see app/db/models/submission_review.py for the full reasoning.
Same shape/conventions as observation_moderation's own migration
(13e123a398eb): explicit constraint/index names, status/rejection_reason as
a small closed vocabulary rather than free text.

NO BACKFILL, unlike observation_moderation's migration. That migration
backfilled because "every Observation must have a moderation row" is an
invariant this codebase maintains going forward. No equivalent invariant
applies here: a submission made before this feature shipped was already
paid immediately under the old (pre-gate) behavior, and its existing
reward_ledger row is untouched by this migration -- it simply has no review
row, and the new admin queue (which only lists rows that exist in this
table) correctly never surfaces it for re-review. Retroactively gating
something already paid, with no reversal mechanism in this codebase, is
explicitly out of scope.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c8f4a1d9e356"
down_revision: Union[str, None] = "9b3f27c5a814"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FK_SUBMISSION = "fk_submission_reviews_submission_id_submissions"
_FK_GUIDE = "fk_submission_reviews_guide_id_guides"
_UQ_SUBMISSION = "uq_submission_reviews_submission_id"
_UQ_IDEMPOTENCY_KEY = "uq_submission_reviews_reward_idempotency_key"
_IX_STATUS_CREATED_AT = "ix_submission_reviews_status_created_at"
_IX_GUIDE_ID = "ix_submission_reviews_guide_id"


def upgrade() -> None:
    op.create_table(
        "submission_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("guide_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending_review"),
        sa.Column("decided_by", sa.String(length=255), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.String(length=50), nullable=True),
        sa.Column("rejection_note", sa.Text(), nullable=True),
        sa.Column("reward_rule_key", sa.String(length=100), nullable=False),
        sa.Column("reward_idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("reward_source_type", sa.String(length=50), nullable=False),
        sa.Column("reward_source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reward_points_awarded", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["submission_id"], ["submissions.id"], name=_FK_SUBMISSION, ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["guide_id"], ["guides.id"], name=_FK_GUIDE, ondelete="CASCADE"),
    )
    op.create_unique_constraint(_UQ_SUBMISSION, "submission_reviews", ["submission_id"])
    op.create_unique_constraint(
        _UQ_IDEMPOTENCY_KEY, "submission_reviews", ["reward_idempotency_key"]
    )
    op.create_index(_IX_STATUS_CREATED_AT, "submission_reviews", ["status", "created_at"])
    op.create_index(_IX_GUIDE_ID, "submission_reviews", ["guide_id"])


def downgrade() -> None:
    op.drop_index(_IX_GUIDE_ID, table_name="submission_reviews")
    op.drop_index(_IX_STATUS_CREATED_AT, table_name="submission_reviews")
    op.drop_constraint(_UQ_IDEMPOTENCY_KEY, "submission_reviews", type_="unique")
    op.drop_constraint(_UQ_SUBMISSION, "submission_reviews", type_="unique")
    op.drop_table("submission_reviews")
