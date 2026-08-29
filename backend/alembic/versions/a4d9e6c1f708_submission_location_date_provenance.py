"""Submission/Observation location and date provenance, plus the 'memory'
capture type.

Adds the columns that let a Submission (and the Observation built from it)
record HOW its coordinate was obtained and WHEN its content actually happened
-- as opposed to only WHERE and WHEN it was submitted, which is all that
existed before. Nothing here is destructive: every new column is additive,
and existing rows get the honest "unknown"/null defaults rather than a
backfilled guess about data that was never recorded.

Revision ID: a4d9e6c1f708
Revises: e7a2c5f81b60
"""

import sqlalchemy as sa
from alembic import op

revision = "a4d9e6c1f708"
down_revision = "e7a2c5f81b60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "submissions",
        sa.Column(
            "location_source", sa.String(length=30), nullable=False, server_default="unknown"
        ),
    )
    op.add_column(
        "submissions", sa.Column("location_accuracy_meters", sa.Numeric(10, 2), nullable=True)
    )
    op.add_column(
        "submissions",
        sa.Column("location_captured_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("submissions", sa.Column("location_label", sa.String(length=255), nullable=True))
    op.add_column("submissions", sa.Column("location_evidence", sa.Text(), nullable=True))
    op.add_column(
        "submissions", sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "submissions",
        sa.Column(
            "occurred_at_precision", sa.String(length=20), nullable=False, server_default="unknown"
        ),
    )
    op.add_column(
        "submissions",
        sa.Column("date_source", sa.String(length=20), nullable=False, server_default="unknown"),
    )

    op.add_column("observations", sa.Column("location_source", sa.String(length=30), nullable=True))
    op.add_column("observations", sa.Column("location_evidence", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("observations", "location_evidence")
    op.drop_column("observations", "location_source")

    op.drop_column("submissions", "date_source")
    op.drop_column("submissions", "occurred_at_precision")
    op.drop_column("submissions", "occurred_at")
    op.drop_column("submissions", "location_evidence")
    op.drop_column("submissions", "location_label")
    op.drop_column("submissions", "location_captured_at")
    op.drop_column("submissions", "location_accuracy_meters")
    op.drop_column("submissions", "location_source")
