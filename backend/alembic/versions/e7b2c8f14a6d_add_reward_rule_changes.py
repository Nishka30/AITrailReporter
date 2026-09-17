"""add reward_rule_changes (points-change audit trail)

Revision ID: e7b2c8f14a6d
Revises: c8f4a1d9e356
Create Date: 2026-09-17

Adds a small, append-only audit table for `reward_rules.points` changes --
who changed a rule's points, what it was, what it became, and when. This is
the ONLY thing this migration adds: `reward_rules` and `reward_ledger`
themselves are untouched, because they already do exactly what an
admin-configurable reward system needs (see app/db/models/reward.py) -- the
missing piece was purely an admin read/write API and UI on top of the
existing `reward_rules` table, not a new reward mechanism.

Deliberately NOT a generic "audit log" for every column on every table --
scoped narrowly to what was asked for (points-change history on reward
rules), same "don't over-engineer" judgment call as the rest of this
codebase's admin-moderation tables. `reward_id` cascades on delete, but
`reward_rules` rows are never actually deleted by any code path in this
codebase (only deactivated via `active=False`), so in practice these rows
outlive their rule for the lifetime of the system.

Changing a rule's points here NEVER rewrites `reward_ledger` -- that table
stores what was actually granted, permanently, per its own docstring. This
table exists purely so an admin can see "who changed this and when," not to
recompute or correct historical awards.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e7b2c8f14a6d"
down_revision: Union[str, None] = "c8f4a1d9e356"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FK_RULE = "fk_reward_rule_changes_rule_id_reward_rules"
_IX_RULE_ID_CHANGED_AT = "ix_reward_rule_changes_rule_id_changed_at"


def upgrade() -> None:
    op.create_table(
        "reward_rule_changes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Denormalized snapshot of the rule's key at change time, same
        # convention reward_ledger.rule_key already uses -- lets this row
        # stay readable even if the rule itself is ever deleted.
        sa.Column("rule_key", sa.String(length=100), nullable=False),
        # Null on the row created alongside a brand-new rule (there is no
        # "previous" value yet).
        sa.Column("previous_points", sa.Integer(), nullable=True),
        sa.Column("new_points", sa.Integer(), nullable=False),
        sa.Column("changed_by", sa.String(length=255), nullable=False),
        sa.Column(
            "changed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["reward_rules.id"], name=_FK_RULE, ondelete="CASCADE"
        ),
    )
    op.create_index(_IX_RULE_ID_CHANGED_AT, "reward_rule_changes", ["rule_id", "changed_at"])


def downgrade() -> None:
    op.drop_index(_IX_RULE_ID_CHANGED_AT, table_name="reward_rule_changes")
    op.drop_table("reward_rule_changes")
