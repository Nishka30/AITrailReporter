"""Places browser: reuses the existing Location table and PostGIS
ST_DWithin/ST_Distance -- no client-side Haversine, no second geodata store.

Category filtering/grouping reuses the existing LocationCategory /
LocationCategoryAssignment tables (see app/services/places/category_catalog.py
and category_assignment.py) -- there is no second, parallel category system
here. app/services/places/category_ui_groups.py only adds a presentation-only
grouping on top of that same data for the admin filter sidebar.
"""

from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.location import Location
from app.db.models.location_category import LocationCategory, LocationCategoryAssignment
from app.db.models.observation import Observation
from app.db.models.observation_moderation import ObservationModeration
from app.schemas.admin import (
    PlaceCategoryDetail,
    PlaceCategoryGroup,
    PlaceCategoryOption,
    PlaceDetail,
    PlaceKnowledgeCoverageDetail,
    PlaceQueueResult,
    PlaceSummary,
)
from app.services import category_knowledge as category_knowledge_service
from app.services.admin_review import ReviewQueueFilters, list_review_queue
from app.services.places import category_assignment
from app.services.places.category_catalog import KIND_PLACE_TYPE
from app.services.places.category_ui_groups import UI_GROUPS, place_type_ui_group


class PlaceFilters:
    def __init__(
        self,
        q: str | None = None,
        category: str | None = None,
        group: str | None = None,
    ):
        self.q = q or None
        # Comma-separated place_type slugs (e.g. "restaurant,cafe") -- a
        # Location matching ANY of them is included (multi-select, OR'd).
        self.category: list[str] = [s for s in category.split(",") if s] if category else []
        # Comma-separated UI group keys (see category_ui_groups.UI_GROUPS) --
        # resolved down to every place_type slug in each named group, then
        # OR'd together with `category` above (selecting both a group and one
        # of its own slugs is redundant but harmless).
        self.group: list[str] = [g for g in group.split(",") if g] if group else []


def _matching_place_type_slugs(filters: PlaceFilters) -> list[str] | None:
    """The place_type slugs the category/group filters resolve to, or None
    if neither filter is active (meaning: don't filter by category)."""
    if not filters.category and not filters.group:
        return None
    slugs: set[str] = set(filters.category)
    if filters.group:
        # Every catalog place_type currently in the DB whose UI group matches
        # one of the requested groups. Computed against the catalog module
        # (not a DB round trip) since it's a small, static, in-memory table.
        from app.services.places.category_catalog import PLACE_TYPES

        for place_type in PLACE_TYPES:
            if place_type_ui_group(place_type.slug) in filters.group:
                slugs.add(place_type.slug)
    return list(slugs)


def _base_query(filters: PlaceFilters):
    radius = settings.geographic_context_radius_meters
    stmt = (
        select(
            Location.id,
            Location.name,
            Location.latitude,
            Location.longitude,
            Location.category,
            Location.subcategory,
            Location.source,
            func.count(Observation.id).label("nearby_count"),
            func.coalesce(
                func.sum(case((ObservationModeration.status == "pending_review", 1), else_=0)), 0
            ).label("pending_count"),
            func.coalesce(
                func.sum(case((ObservationModeration.status == "approved", 1), else_=0)), 0
            ).label("approved_count"),
        )
        .outerjoin(
            Observation,
            (Observation.geog.isnot(None)) & (func.ST_DWithin(Observation.geog, Location.geog, radius)),
        )
        .outerjoin(ObservationModeration, ObservationModeration.observation_id == Observation.id)
    )
    if filters.q:
        stmt = stmt.where(Location.name.ilike(f"%{filters.q}%"))

    slugs = _matching_place_type_slugs(filters)
    if slugs is not None:
        # A separate EXISTS-style subquery on location_id, not a join, so the
        # observation/moderation aggregation above never fans out across
        # multiple category assignments for the same Location.
        stmt = stmt.where(
            Location.id.in_(
                select(LocationCategoryAssignment.location_id)
                .join(
                    LocationCategory,
                    LocationCategory.id == LocationCategoryAssignment.category_id,
                )
                .where(
                    LocationCategory.kind == KIND_PLACE_TYPE,
                    LocationCategory.slug.in_(slugs),
                )
            )
        )

    return stmt.group_by(
        Location.id,
        Location.name,
        Location.latitude,
        Location.longitude,
        Location.category,
        Location.subcategory,
        Location.source,
    )


def list_places(
    db: Session, filters: PlaceFilters, page: int, page_size: int
) -> PlaceQueueResult:
    stmt = _base_query(filters)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    stmt = stmt.order_by(Location.name).offset((page - 1) * page_size).limit(page_size)
    rows = db.execute(stmt).all()

    items = [
        PlaceSummary(
            location_id=row.id,
            name=row.name,
            latitude=float(row.latitude),
            longitude=float(row.longitude),
            category=row.category,
            subcategory=row.subcategory,
            source=row.source,
            nearby_observation_count=row.nearby_count,
            pending_review_count=row.pending_count,
            approved_count=row.approved_count,
            categories=[
                PlaceCategoryDetail(**vars(c))
                for c in category_assignment.list_location_categories(db, row.id)
            ],
        )
        for row in rows
    ]
    return PlaceQueueResult(items=items, total=total, page=page, page_size=page_size)


def get_place_detail(db: Session, location_id: UUID, limit: int = 25) -> PlaceDetail | None:
    location = db.get(Location, location_id)
    if location is None:
        return None

    result = list_review_queue(
        db, ReviewQueueFilters(place_id=location_id, sort="observed_at"), page=1, page_size=limit
    )
    return PlaceDetail(
        location_id=location.id,
        name=location.name,
        description=location.description,
        latitude=float(location.latitude),
        longitude=float(location.longitude),
        category=location.category,
        subcategory=location.subcategory,
        source=location.source,
        provider=location.provider,
        external_place_id=location.external_place_id,
        formatted_address=location.formatted_address,
        categories=[
            PlaceCategoryDetail(**vars(category))
            for category in category_assignment.list_location_categories(
                db, location.id
            )
        ],
        created_at=location.created_at,
        recent_observations=result.items,
        # PRIMARY (category-driven) knowledge coverage -- separate from the
        # legacy/new category lists above, which only say WHAT this place is,
        # not what TrailMind actually knows and trusts about it yet. Hazard
        # state (KnowledgeTypeConfig) and general Explore prompts are
        # deliberately NOT folded in here -- see services/category_knowledge.py's
        # module docstring: this dashboard is the PRIMARY system's view only.
        knowledge_coverage=[
            PlaceKnowledgeCoverageDetail(
                category_assignment_id=cov.category_assignment_id,
                slug=cov.slug,
                kind=cov.kind,
                display_name=cov.display_name,
                relevance=cov.relevance,
                is_primary=cov.is_primary,
                state=cov.state,
                verified_item_count=len(cov.stale_items),
                last_verified_at=max(
                    (item.last_verified_at for item in cov.stale_items if item.last_verified_at),
                    default=None,
                ),
                next_stale_at=max(
                    (
                        category_knowledge_service.stale_at(item)
                        for item in cov.stale_items
                        if category_knowledge_service.is_fresh(item, datetime.now(timezone.utc))
                    ),
                    default=None,
                ),
            )
            for cov in category_knowledge_service.get_location_coverage(db, location.id)
        ],
    )


def list_category_filter_options(db: Session) -> list[PlaceCategoryGroup]:
    """Every place_type currently assigned to at least one Location, grouped
    into the user-friendly sections from category_ui_groups.py, each with the
    number of DISTINCT Locations carrying it (never a raw assignment-row
    count -- a Location assigned the same category twice does not exist by
    construction (UNIQUE(location_id, category_id)), but counting distinct
    location ids in Python here keeps that guarantee explicit rather than
    assumed).

    One query, then pure-Python aggregation -- the catalog is small (~230
    rows) and even a few thousand assignment rows is trivial to aggregate in
    memory, so there is no need for a cached/materialized count here (see the
    module docstring's "no second category system" note: this reads the same
    assignment table every other consumer does, just once per request).
    """
    rows = db.execute(
        select(
            LocationCategoryAssignment.location_id,
            LocationCategory.slug,
            LocationCategory.display_name,
            LocationCategory.default_priority,
        )
        .join(LocationCategory, LocationCategory.id == LocationCategoryAssignment.category_id)
        .where(LocationCategory.kind == KIND_PLACE_TYPE, LocationCategory.active.is_(True))
    ).all()

    locations_by_slug: dict[str, set] = defaultdict(set)
    slug_meta: dict[str, tuple[str, int]] = {}
    for location_id, slug, display_name, priority in rows:
        locations_by_slug[slug].add(location_id)
        slug_meta[slug] = (display_name, priority)

    group_locations: dict[str, set] = defaultdict(set)
    group_options: dict[str, list[PlaceCategoryOption]] = defaultdict(list)
    for slug, location_ids in locations_by_slug.items():
        group_key = place_type_ui_group(slug)
        display_name, priority = slug_meta[slug]
        group_locations[group_key] |= location_ids
        group_options[group_key].append(
            PlaceCategoryOption(
                kind=KIND_PLACE_TYPE,
                slug=slug,
                display_name=display_name,
                group=group_key,
                count=len(location_ids),
                priority=priority,
            )
        )

    groups: list[PlaceCategoryGroup] = []
    for group_key, group_label in UI_GROUPS:
        options = group_options.get(group_key)
        if not options:
            continue
        # Highest catalog priority first (the existing default_priority
        # values, never modified here), then by usage, then alphabetically --
        # this is what "Show more" reveals further down.
        options.sort(key=lambda o: (-o.priority, -o.count, o.display_name))
        groups.append(
            PlaceCategoryGroup(
                key=group_key,
                label=group_label,
                count=len(group_locations[group_key]),
                options=options,
            )
        )

    # Most-used groups first, "Other" always last regardless of its count.
    groups.sort(key=lambda g: (g.key == "other", -g.count))
    return groups
