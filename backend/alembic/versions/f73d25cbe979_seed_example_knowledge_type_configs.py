"""seed example knowledge type configs

Revision ID: f73d25cbe979
Revises: 6d02f3b18564
Create Date: 2026-08-26 13:20:48.905410

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f73d25cbe979'
down_revision: Union[str, None] = '6d02f3b18564'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

knowledge_type_config = sa.table(
    "knowledge_type_config",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("knowledge_type", sa.String),
    sa.column("display_name", sa.String),
    sa.column("freshness_window_hours", sa.Integer),
    sa.column("aging_threshold_hours", sa.Integer),
    sa.column("geographic_relevance_radius_meters", sa.Integer),
    sa.column("default_priority", sa.Integer),
    sa.column("safety_critical", sa.Boolean),
    sa.column("active", sa.Boolean),
)

SEED_ROWS = [
    {
        "knowledge_type": "weather",
        "display_name": "Weather",
        "freshness_window_hours": 6,
        "aging_threshold_hours": 3,
        "geographic_relevance_radius_meters": 10000,
        "default_priority": 5,
        "safety_critical": True,
    },
    {
        "knowledge_type": "trail_condition",
        "display_name": "Trail Condition",
        "freshness_window_hours": 72,
        "aging_threshold_hours": 24,
        "geographic_relevance_radius_meters": 2000,
        "default_priority": 4,
        "safety_critical": False,
    },
    {
        "knowledge_type": "snow_ice",
        "display_name": "Snow / Ice",
        "freshness_window_hours": 24,
        "aging_threshold_hours": 12,
        "geographic_relevance_radius_meters": 2000,
        "default_priority": 5,
        "safety_critical": True,
    },
    {
        "knowledge_type": "obstruction",
        "display_name": "Obstruction",
        "freshness_window_hours": 168,
        "aging_threshold_hours": 72,
        "geographic_relevance_radius_meters": 500,
        "default_priority": 4,
        "safety_critical": True,
    },
]


def upgrade() -> None:
    op.bulk_insert(
        knowledge_type_config,
        [
            {
                "id": uuid.uuid4(),
                "active": True,
                **row,
            }
            for row in SEED_ROWS
        ],
    )


def downgrade() -> None:
    conn = op.get_bind()
    types = [row["knowledge_type"] for row in SEED_ROWS]
    conn.execute(
        knowledge_type_config.delete().where(
            knowledge_type_config.c.knowledge_type.in_(types)
        )
    )
