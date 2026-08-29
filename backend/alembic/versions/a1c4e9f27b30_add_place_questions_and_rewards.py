"""add place questions and rewards

Revision ID: a1c4e9f27b30
Revises: 13e123a398eb
Create Date: 2026-08-28 00:00:00.000000

Step 18: a SECOND question source (popular questions about a place, researched
from the web) and a reward-points system.

Purely additive. Nothing in the existing knowledge-gap pipeline is altered:
`questions`, `question_assignments`, `question_answers`, `observations` and
`observation_moderation` are untouched, and the only change to an existing
table is one new NULLABLE column on `submissions`.

Four new tables:

  place_questions          -- the researched questions, one row per question
                              per Location. UNIQUE (location_id,
                              normalized_text) makes dedup a DATABASE
                              guarantee rather than an application convention.
  place_question_research  -- the research lifecycle per Location (a SEVENTH
                              state machine, same shape as transcriptions /
                              extractions). Its researched_at is what prevents
                              re-searching the web on every request.
  reward_rules             -- what each kind of contribution is worth. A table
                              so amounts change without a deploy and a new
                              earning opportunity is an INSERT, not code.
  reward_ledger            -- append-only awards. UNIQUE(idempotency_key) is
                              the duplicate-prevention mechanism for offline
                              sync; see app/db/models/reward.py.

NO BACKFILL, and none is needed. Unlike 13e123a398eb (where every existing
Observation genuinely needed a moderation row to preserve an invariant), a
Location that has never been researched genuinely has no popular questions,
and a guide who contributed before rewards existed genuinely has no ledger
entries. Empty is the truthful state here, not a "not yet migrated" placeholder
-- and retroactively minting points for past contributions would invent
earnings nobody was promised.

reward_rules IS seeded, because a rule table with no rows would make every
award silently resolve to nothing. Seeded values are starting points meant to
be tuned operationally -- see the note on their real monetary value below.

Constraint/index names are explicit, matching this project's convention.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1c4e9f27b30'
down_revision: Union[str, None] = '13e123a398eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FK_PQ_LOCATION = "fk_place_questions_location_id_locations"
_UQ_PQ_LOCATION_NORMALIZED = "uq_place_questions_location_normalized"
_FK_PQR_LOCATION = "fk_place_question_research_location_id_locations"
_UQ_PQR_LOCATION = "uq_place_question_research_location_id"
_IX_PQR_STATUS = "ix_place_question_research_status"
_UQ_REWARD_RULES_KEY = "uq_reward_rules_rule_key"
_FK_LEDGER_GUIDE = "fk_reward_ledger_guide_id_guides"
_UQ_LEDGER_IDEMPOTENCY = "uq_reward_ledger_idempotency_key"
_IX_LEDGER_GUIDE_AWARDED_AT = "ix_reward_ledger_guide_id_awarded_at"
_FK_SUBMISSION_PLACE_QUESTION = "fk_submissions_source_place_question_id_place_questions"
_IX_SUBMISSION_PLACE_QUESTION = "ix_submissions_source_place_question_id"


def upgrade() -> None:
    op.create_table(
        'place_questions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('location_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('question_text', sa.Text(), nullable=False),
        sa.Column('normalized_text', sa.Text(), nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('source_urls', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('research_batch_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['location_id'], ['locations.id'], name=_FK_PQ_LOCATION, ondelete='CASCADE'
        ),
    )
    op.create_unique_constraint(
        _UQ_PQ_LOCATION_NORMALIZED, 'place_questions', ['location_id', 'normalized_text']
    )

    op.create_table(
        'place_question_research',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('location_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('provider', sa.String(length=50), nullable=False, server_default='anthropic'),
        sa.Column('model', sa.String(length=100), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('researched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['location_id'], ['locations.id'], name=_FK_PQR_LOCATION, ondelete='CASCADE'
        ),
    )
    op.create_unique_constraint(_UQ_PQR_LOCATION, 'place_question_research', ['location_id'])
    op.create_index(_IX_PQR_STATUS, 'place_question_research', ['status'])

    op.create_table(
        'reward_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('rule_key', sa.String(length=100), nullable=False),
        sa.Column('points', sa.Integer(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_unique_constraint(_UQ_REWARD_RULES_KEY, 'reward_rules', ['rule_key'])

    op.create_table(
        'reward_ledger',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('guide_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('points', sa.Integer(), nullable=False),
        sa.Column('rule_key', sa.String(length=100), nullable=False),
        sa.Column('idempotency_key', sa.String(length=255), nullable=False),
        sa.Column('source_type', sa.String(length=50), nullable=False),
        sa.Column('source_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('awarded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['guide_id'], ['guides.id'], name=_FK_LEDGER_GUIDE, ondelete='CASCADE'
        ),
    )
    op.create_unique_constraint(_UQ_LEDGER_IDEMPOTENCY, 'reward_ledger', ['idempotency_key'])
    op.create_index(_IX_LEDGER_GUIDE_AWARDED_AT, 'reward_ledger', ['guide_id', 'awarded_at'])

    # One new NULLABLE column -- the only change to a pre-existing table in
    # this migration. Every existing submission correctly stays NULL forever
    # (it genuinely did not answer a place question), so no backfill applies.
    op.add_column(
        'submissions',
        sa.Column('source_place_question_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        _FK_SUBMISSION_PLACE_QUESTION,
        'submissions',
        'place_questions',
        ['source_place_question_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index(_IX_SUBMISSION_PLACE_QUESTION, 'submissions', ['source_place_question_id'])

    # Seed the rule table. These are STARTING VALUES, deliberately modest:
    # at the configured conversion of 10 points = $1.00 (see
    # settings.reward_points_per_currency_unit) a 25-point answer is worth
    # $2.50 of real money, so these are meant to be reviewed operationally
    # before any real payout mechanism exists. Changing them is an UPDATE on
    # this table -- no deploy, and no effect on points already awarded (the
    # ledger stores the points it actually granted).
    op.execute(
        """
        INSERT INTO reward_rules (id, rule_key, points, description, active, created_at, updated_at)
        VALUES
          (gen_random_uuid(), 'question_answer', 25,
           'Answering a question from your priority queue', true, now(), now()),
          (gen_random_uuid(), 'question_answer_safety_critical', 40,
           'Answering a safety-critical question from your priority queue', true, now(), now()),
          (gen_random_uuid(), 'place_question_answer', 15,
           'Answering a popular question about a place', true, now(), now()),
          (gen_random_uuid(), 'explore_contribution', 20,
           'Sharing a discovery from the Explore tab', true, now(), now()),
          (gen_random_uuid(), 'explore_contribution_media_bonus', 30,
           'Bonus for adding a photo or voice note to an Explore discovery', true, now(), now())
        """
    )


def downgrade() -> None:
    op.drop_index(_IX_SUBMISSION_PLACE_QUESTION, table_name='submissions')
    op.drop_constraint(_FK_SUBMISSION_PLACE_QUESTION, 'submissions', type_='foreignkey')
    op.drop_column('submissions', 'source_place_question_id')

    op.drop_index(_IX_LEDGER_GUIDE_AWARDED_AT, table_name='reward_ledger')
    op.drop_constraint(_UQ_LEDGER_IDEMPOTENCY, 'reward_ledger', type_='unique')
    op.drop_table('reward_ledger')

    op.drop_constraint(_UQ_REWARD_RULES_KEY, 'reward_rules', type_='unique')
    op.drop_table('reward_rules')

    op.drop_index(_IX_PQR_STATUS, table_name='place_question_research')
    op.drop_constraint(_UQ_PQR_LOCATION, 'place_question_research', type_='unique')
    op.drop_table('place_question_research')

    op.drop_constraint(_UQ_PQ_LOCATION_NORMALIZED, 'place_questions', type_='unique')
    op.drop_table('place_questions')
