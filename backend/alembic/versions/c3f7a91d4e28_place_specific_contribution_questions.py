"""Turn place questions into location-specific contribution invitations

Adds `contribution_kind` and `context_note` to place_questions, and seeds a
per-kind reward rate for each kind.

WHY THE EXISTING ROWS ARE RETIRED HERE
--------------------------------------
The previous research prompt asked "what do travellers commonly ask about this
place?" and answered it correctly -- producing reader-facing FAQs like "Is it
safe to cross the Hillary Bridge if you're scared of heights?". Those are not
answerable by a guide standing on the bridge, which is the entire point of this
feature. They cannot be salvaged by backfilling a column: the TEXT itself is
addressed to the wrong person.

So this migration deactivates every existing place_question and clears
`researched_at` on every research row. Nothing is deleted -- an answered
question must keep existing so its answer's provenance still resolves (see
PlaceQuestion.active). Clearing researched_at makes each place look stale to
place_questions.is_research_stale(), so the next request for that place
re-researches it under the new prompt. The cost is one web search per place,
incurred lazily on demand rather than for every place up front.

REWARD VALUES -- READ BEFORE CHANGING
-------------------------------------
These interact with settings.reward_points_per_currency_unit, which is 10
(10 points = $1.00). At that rate the values seeded below are worth:

    place_question_photo        50 pts = $5.00
    place_question_voice        45 pts = $4.50
    place_question_experience   35 pts = $3.50
    place_question_observation  25 pts = $2.50
    place_question_status       15 pts = $1.50

That is real money per contribution. The values are differentiated by genuine
effort (taking and describing a photo vs. confirming a stall is open) as
requested, but they are deliberately called out here because the conversion
rate makes them consequential. They are ordinary table rows: changing one is an
UPDATE on reward_rules, with no deploy and no app release.

The pre-existing `place_question_answer` rule is KEPT, unchanged, as the
fallback rate for any kind that has no rule of its own (see
rewards.place_question_rule_key) -- so adding a sixth kind later cannot
silently pay zero.

Revision ID: c3f7a91d4e28
Revises: a1c4e9f27b30
"""

from alembic import op
import sqlalchemy as sa


revision = "c3f7a91d4e28"
down_revision = "a1c4e9f27b30"
branch_labels = None
depends_on = None


# (rule_key, points, description). Descriptions are what the mobile Rewards
# screen renders verbatim -- it reads them from the same rows the award is paid
# from, so what is advertised can never drift from what is granted.
_KIND_RULES = [
    (
        "place_question_photo",
        50,
        "Photographing a specific place you're standing at",
    ),
    (
        "place_question_voice",
        45,
        "Recording your experience of a specific place",
    ),
    (
        "place_question_experience",
        35,
        "Describing what a specific place is really like",
    ),
    (
        "place_question_observation",
        25,
        "Reporting what you can see at a specific place",
    ),
    (
        "place_question_status",
        15,
        "Confirming whether a place is open or accessible right now",
    ),
]


def upgrade() -> None:
    op.add_column(
        "place_questions",
        sa.Column(
            "contribution_kind",
            sa.String(length=20),
            nullable=False,
            server_default="observation",
        ),
    )
    op.add_column(
        "place_questions",
        sa.Column("context_note", sa.Text(), nullable=True),
    )

    # Retire the reader-facing questions produced by the previous prompt, and
    # make every place due for re-research. See the module docstring.
    op.execute("UPDATE place_questions SET active = false")
    op.execute("UPDATE place_question_research SET researched_at = NULL")

    for rule_key, points, description in _KIND_RULES:
        op.execute(
            sa.text(
                """
                INSERT INTO reward_rules (id, rule_key, points, description, active)
                VALUES (gen_random_uuid(), :rule_key, :points, :description, true)
                ON CONFLICT (rule_key) DO NOTHING
                """
            ).bindparams(rule_key=rule_key, points=points, description=description)
        )


def downgrade() -> None:
    for rule_key, _points, _description in _KIND_RULES:
        op.execute(
            sa.text("DELETE FROM reward_rules WHERE rule_key = :rule_key").bindparams(
                rule_key=rule_key
            )
        )
    # Deliberately NOT reactivating the questions deactivated above: they were
    # retired because their text is wrong for this feature, and a downgrade of
    # the schema is not a reason to put them back in front of guides. Ledger
    # entries already awarded under the removed rules are untouched -- the
    # ledger records the points it actually granted (see RewardRule's docstring).
    op.drop_column("place_questions", "context_note")
    op.drop_column("place_questions", "contribution_kind")
