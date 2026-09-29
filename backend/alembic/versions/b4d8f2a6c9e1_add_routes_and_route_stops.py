"""add routes and route_stops (route strip)

Revision ID: b4d8f2a6c9e1
Revises: 35a9a5a1050a
Create Date: 2026-09-29

Introduces a Route/RouteStop model: a named, ordered sequence of existing
Locations (e.g. a trek), for the public Travelers site's "route strip"
feature. Genuinely new -- there was no route/trail/sequence concept anywhere
in this codebase before this migration.

`route_stops` references `locations.id` by FK only and stores no geography
of its own -- a stop's position IS its Location's own `geog`, reached via
the FK (see app/db/models/route.py for the full reasoning, which mirrors why
CuratedHub points at a Location rather than owning its own place data).

No seed data here -- see scripts/seed_routes.py, run by hand, for the first
example route (Everest Base Camp Trek). Migrations create structure; they
never seed application content in this codebase (see submission_review's own
migration for the same "no backfill of application data" convention).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b4d8f2a6c9e1"
down_revision: Union[str, None] = "35a9a5a1050a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UQ_ROUTES_SLUG = "uq_routes_slug"
_FK_ROUTE_STOPS_ROUTE = "fk_route_stops_route_id_routes"
_FK_ROUTE_STOPS_LOCATION = "fk_route_stops_location_id_locations"
_UQ_ROUTE_STOPS_ROUTE_LOCATION = "uq_route_stops_route_location"
_UQ_ROUTE_STOPS_ROUTE_SEQUENCE = "uq_route_stops_route_sequence_order"
_IX_ROUTE_STOPS_ROUTE_SEQUENCE = "ix_route_stops_route_id_sequence_order"
_IX_ROUTE_STOPS_LOCATION = "ix_route_stops_location_id"


def upgrade() -> None:
    op.create_table(
        "routes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=150), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name=_UQ_ROUTES_SLUG),
    )
    op.create_table(
        "route_stops",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("route_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_order", sa.Integer(), nullable=False),
        sa.Column("stop_label", sa.String(length=255), nullable=True),
        sa.Column("elevation_meters", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["route_id"], ["routes.id"], name=_FK_ROUTE_STOPS_ROUTE, ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["location_id"], ["locations.id"], name=_FK_ROUTE_STOPS_LOCATION, ondelete="CASCADE"
        ),
        sa.UniqueConstraint("route_id", "location_id", name=_UQ_ROUTE_STOPS_ROUTE_LOCATION),
        sa.UniqueConstraint("route_id", "sequence_order", name=_UQ_ROUTE_STOPS_ROUTE_SEQUENCE),
    )
    op.create_index(_IX_ROUTE_STOPS_ROUTE_SEQUENCE, "route_stops", ["route_id", "sequence_order"])
    op.create_index(_IX_ROUTE_STOPS_LOCATION, "route_stops", ["location_id"])


def downgrade() -> None:
    op.drop_index(_IX_ROUTE_STOPS_LOCATION, table_name="route_stops")
    op.drop_index(_IX_ROUTE_STOPS_ROUTE_SEQUENCE, table_name="route_stops")
    op.drop_table("route_stops")
    op.drop_table("routes")
