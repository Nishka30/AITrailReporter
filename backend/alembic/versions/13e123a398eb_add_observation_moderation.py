"""add observation moderation

Revision ID: 13e123a398eb
Revises: 386c20775143
Create Date: 2026-08-28 00:00:00.000000

Admin content-moderation layer: introduces the concept of "is this observation
approved for eventual public visibility" as a SIXTH independent lifecycle,
alongside the mobile app's sync_status, Transcription.status,
Extraction.status, Question.status, and QuestionAssignment.status. None of
those existing state machines are touched by this migration.

Deliberately a NEW table (observation_moderation), one row per Observation via
a UNIQUE foreign key, rather than status columns added directly to
Observation -- mirrors this codebase's existing convention (Transcription/
Extraction/Question are each their own table rather than columns on their
parent). See app/db/models/observation_moderation.py for the full reasoning.

Purely additive: no existing table/column is altered. A backfill INSERT gives
every Observation that already exists a 'pending_review' row, so the "an
Observation should never exist without a moderation row" invariant holds for
data that predates this migration too -- new Observations get their row
created atomically at extraction time (see app/services/extractions.py),
never by this migration again.

Constraint/index names are explicit, matching this project's own established
convention (see 386c20775143's docstring for why leaving it to autogenerate's
default naming was a problem before).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '13e123a398eb'
down_revision: Union[str, None] = '386c20775143'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FK_OBSERVATION = "fk_observation_moderation_observation_id_observations"
_UQ_OBSERVATION = "uq_observation_moderation_observation_id"
_IX_STATUS_CREATED_AT = "ix_observation_moderation_status_created_at"


def upgrade() -> None:
    op.create_table(
        'observation_moderation',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('observation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending_review'),
        sa.Column('decided_by', sa.String(length=255), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejection_reason', sa.String(length=50), nullable=True),
        sa.Column('rejection_note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['observation_id'], ['observations.id'], name=_FK_OBSERVATION, ondelete='CASCADE'
        ),
    )
    op.create_unique_constraint(_UQ_OBSERVATION, 'observation_moderation', ['observation_id'])
    op.create_index(_IX_STATUS_CREATED_AT, 'observation_moderation', ['status', 'created_at'])

    # Backfill: every Observation that already exists gets a 'pending_review'
    # row, same as a freshly-extracted one would. Nothing here approves or
    # rejects anything -- pending_review is the one honest default for
    # observations no admin has looked at yet.
    op.execute(
        """
        INSERT INTO observation_moderation (id, observation_id, status, created_at, updated_at)
        SELECT gen_random_uuid(), o.id, 'pending_review', now(), now()
        FROM observations o
        """
    )


def downgrade() -> None:
    op.drop_index(_IX_STATUS_CREATED_AT, table_name='observation_moderation')
    op.drop_constraint(_UQ_OBSERVATION, 'observation_moderation', type_='unique')
    op.drop_table('observation_moderation')
