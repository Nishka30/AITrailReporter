"""Persisting a Location's categories, and keeping the catalog in step.

This is the only module that writes `location_category_assignments`. Callers
hand it a Location; it works out the categories (via category_rules, and
optionally the constrained model fallback) and reconciles the rows.

THREE PROPERTIES THAT MATTER, AND WHY:

1. IDEMPOTENT. Re-classifying a place must converge, not accumulate. Running
   this twice on the same Location leaves exactly the same rows -- otherwise
   a place re-discovered every month would grow a longer and longer tail of
   categories, which is precisely the "too many weak categories" failure this
   system is supposed to avoid.

2. A HUMAN'S JUDGEMENT IS NEVER OVERWRITTEN. `source='manual'` assignments
   survive every automatic run untouched, and an automatic pass will not
   re-add a category a human deleted. Same protection curated seed questions
   already have from AI research refreshes -- if a person has looked at a
   place and decided, that decision outranks a rule.

3. NEVER RAISES INTO A CALLER'S CRITICAL PATH. Classification is enrichment.
   A place must still be discovered, stored and offered to a guide even if
   categorising it fails, so the call sites use `maybe_assign_categories`,
   matching the best-effort convention `maybe_ensure_discovered` established.
"""

import logging
from dataclasses import dataclass

from sqlalchemy import func, null, select
from sqlalchemy.orm import Session

from app.db.geo import make_point
from app.db.models.location import Location
from app.db.models.location_category import (
    LocationCategory,
    LocationCategoryAssignment,
)
from app.services.places import category_catalog as catalog
from app.services.places import category_rules

logger = logging.getLogger(__name__)

# AUTHORITY TIERS. A classification pass may replace assignments of its own
# tier or below, and never above.
#
# This is what stops the cheap pass destroying the expensive one. The free
# deterministic backfill is safe to run over the whole table at any time --
# but Thamel's categories (Shopping, Food, Trekking, Nightlife) exist only
# because a model was PAID to work them out, and rules cannot reproduce them.
# Without tiers, one routine re-run of the free pass would silently delete
# every one of them, and the next sweep would pay for the same answer again.
#
# Manual sits above both for the reason stated in property 2: a person who
# has looked at a place outranks anything automatic.
_TIER_DETERMINISTIC = 0
_TIER_AI = 1
_TIER_MANUAL = 2

_SOURCE_TIER: dict[str, int] = {
    "seed_type": _TIER_DETERMINISTIC,
    "google_type": _TIER_DETERMINISTIC,
    "name_rule": _TIER_DETERMINISTIC,
    "rule_implied": _TIER_DETERMINISTIC,
    "ai": _TIER_AI,
    "manual": _TIER_MANUAL,
}


def _tier_of(source: str) -> int:
    # An unrecognised source is treated as the most protected, so a future
    # source added without updating this table fails safe (never silently
    # deleted) rather than fails destructive.
    return _SOURCE_TIER.get(source, _TIER_MANUAL)

# Process-level cache of the catalog's (kind, slug) -> id map. The catalog is
# ~231 rows that change only when a human edits the vocabulary, while a single
# discovery batch classifies up to 20 places -- re-reading it per place would
# be pure waste. Call reset_catalog_cache() after editing the catalog in a
# long-lived process.
_catalog_cache: dict[tuple[str, str], "CatalogEntry"] | None = None


@dataclass(frozen=True)
class CatalogEntry:
    id: object
    kind: str
    slug: str
    display_name: str
    default_priority: int
    active: bool


@dataclass(frozen=True)
class AssignedCategory:
    """A persisted assignment, joined to its catalog row -- what every reader
    (API, prompt builder, admin) actually wants."""

    kind: str
    slug: str
    display_name: str
    relevance: int
    confidence: float
    is_primary: bool
    source: str


def reset_catalog_cache() -> None:
    global _catalog_cache
    _catalog_cache = None


def _load_catalog(db: Session) -> dict[tuple[str, str], CatalogEntry]:
    global _catalog_cache
    if _catalog_cache is None:
        rows = db.execute(select(LocationCategory)).scalars().all()
        _catalog_cache = {
            (row.kind, row.slug): CatalogEntry(
                id=row.id,
                kind=row.kind,
                slug=row.slug,
                display_name=row.display_name,
                default_priority=row.default_priority,
                active=row.active,
            )
            for row in rows
        }
    return _catalog_cache


# --- Catalog sync -------------------------------------------------------------


def sync_category_catalog(db: Session) -> tuple[int, int]:
    """Bring `location_categories` in line with category_catalog.py.

    Returns (created, updated). Idempotent, and safe to run against a
    populated database: it inserts vocabulary that is missing and refreshes
    display name / priority / description / provenance on rows that have
    drifted, but NEVER deletes -- assignments reference these rows, and a
    category that is no longer wanted is retired with `active=False` rather
    than destroyed.

    The initial seed happens in the migration (a frozen copy, as migrations
    require). This is how the catalog grows afterwards without a migration
    per vocabulary tweak.
    """
    existing = {
        (row.kind, row.slug): row
        for row in db.execute(select(LocationCategory)).scalars().all()
    }
    created = 0
    updated = 0

    definitions: list[tuple[str, object]] = [
        (catalog.KIND_THEME, theme) for theme in catalog.THEMES
    ] + [(catalog.KIND_PLACE_TYPE, place_type) for place_type in catalog.PLACE_TYPES]

    for kind, definition in definitions:
        row = existing.get((kind, definition.slug))
        if row is None:
            db.add(
                LocationCategory(
                    kind=kind,
                    slug=definition.slug,
                    display_name=definition.display_name,
                    default_priority=definition.default_priority,
                    description=definition.description,
                    touristlink_id=definition.touristlink_id,
                    active=True,
                )
            )
            created += 1
            continue
        changed = False
        for attribute, value in (
            ("display_name", definition.display_name),
            ("default_priority", definition.default_priority),
            ("description", definition.description),
            ("touristlink_id", definition.touristlink_id),
        ):
            if getattr(row, attribute) != value:
                setattr(row, attribute, value)
                changed = True
        if changed:
            updated += 1

    if created or updated:
        db.flush()
        reset_catalog_cache()
    return created, updated


# --- Assignment ---------------------------------------------------------------


def proposals_for_location(
    location: Location,
) -> list[category_rules.ProposedCategory]:
    """Deterministic proposals derived from what the Location already knows
    about itself. Reads only stored fields -- no network, no model."""
    # A curated seed row carries the curator's own free-text type in
    # `place_kind` (see seed_import.py); a Google-discovered row carries
    # Google's raw type there instead, which google_primary_type already
    # covers. Passing place_kind as a seed type for a non-seed row would
    # feed Google vocabulary into the curated-type table, so it is gated.
    seed_type = location.place_kind if location.provider == "seed" else None
    return category_rules.classify_categories(
        primary_type=location.google_primary_type,
        types=location.google_types,
        name=location.name,
        seed_type=seed_type,
        legacy_subcategory=location.subcategory,
    )


def assign_categories(
    db: Session,
    location: Location,
    *,
    proposals: list[category_rules.ProposedCategory] | None = None,
) -> list[AssignedCategory]:
    """Reconcile this Location's category assignments to `proposals`
    (deterministic ones by default). Flushes; does not commit -- the caller
    owns the transaction, exactly like the rest of the discovery path.

    The pass's authority tier is taken from the proposals' own sources, so a
    caller cannot accidentally grant itself more authority than the evidence
    it is carrying: rule output can only ever replace rule output, model
    output can replace rules and earlier model output, and neither touches a
    human's. See _SOURCE_TIER.
    """
    if proposals is None:
        proposals = proposals_for_location(location)

    tier = max(
        (_tier_of(proposal.source) for proposal in proposals),
        default=_TIER_DETERMINISTIC,
    )

    entries = _load_catalog(db)
    existing = (
        db.execute(
            select(LocationCategoryAssignment).where(
                LocationCategoryAssignment.location_id == location.id
            )
        )
        .scalars()
        .all()
    )
    by_category_id = {row.category_id: row for row in existing}

    replaceable = [row for row in existing if _tier_of(row.source) <= tier]
    protected = [row for row in existing if _tier_of(row.source) > tier]
    # A protected row also VETOES a proposal for the same category --
    # otherwise this pass would overwrite the very judgement the tier exists
    # to defend (a curator's adjusted relevance, or a model's reasoning about
    # a place rules cannot describe).
    protected_category_ids = {row.category_id for row in protected}
    # A kind whose primary is already held by a protected row cannot have its
    # primary reassigned here -- that row is not ours to unset, and the
    # partial unique index permits only one.
    protected_primary_kinds = {row.kind for row in protected if row.is_primary}

    resolved: list[tuple[CatalogEntry, category_rules.ProposedCategory]] = []
    for proposal in proposals:
        entry = entries.get((proposal.kind, proposal.slug))
        if entry is None:
            logger.warning(
                "Skipped category %s/%s for %r: not in catalog.",
                proposal.kind,
                proposal.slug,
                location.name,
            )
            continue
        if not entry.active or entry.id in protected_category_ids:
            continue
        resolved.append((entry, proposal))

    wanted_ids = {entry.id for entry, _ in resolved}

    # Drop this tier's own assignments that this pass no longer proposes.
    # This is what makes re-classification converge rather than accumulate.
    for row in replaceable:
        if row.category_id not in wanted_ids:
            db.delete(row)

    # Clear every primary flag this pass owns BEFORE setting new ones. The
    # partial unique index is checked per statement, so flipping the primary
    # from one category to another in a single pass would collide if the new
    # flag were set while the old one still stood.
    for row in replaceable:
        if row.is_primary:
            row.is_primary = False
    db.flush()

    for entry, proposal in resolved:
        # Never claim a primary a protected row already holds.
        is_primary = proposal.is_primary and proposal.kind not in protected_primary_kinds
        row = by_category_id.get(entry.id)
        if row is None:
            db.add(
                LocationCategoryAssignment(
                    location_id=location.id,
                    category_id=entry.id,
                    kind=proposal.kind,
                    relevance=proposal.relevance,
                    confidence=proposal.confidence,
                    is_primary=is_primary,
                    source=proposal.source,
                    rationale=proposal.rationale,
                )
            )
            continue
        row.kind = proposal.kind
        row.relevance = proposal.relevance
        row.confidence = proposal.confidence
        row.is_primary = is_primary
        row.source = proposal.source
        row.rationale = proposal.rationale

    db.flush()
    return list_location_categories(db, location.id)


def maybe_assign_categories(db: Session, location: Location) -> None:
    """Best-effort `assign_categories`. Never raises.

    Categorising a place is enrichment: a failure here must not stop the
    place being discovered, stored or offered to a guide. Same convention as
    poi_discovery.maybe_ensure_discovered.
    """
    try:
        assign_categories(db, location)
    except Exception as exc:  # noqa: BLE001 -- deliberate best-effort boundary
        logger.warning(
            "Best-effort category assignment failed for %r: %s",
            location.name,
            type(exc).__name__,
        )


# --- Reads --------------------------------------------------------------------


def list_location_categories(
    db: Session, location_id, *, kind: str | None = None
) -> list[AssignedCategory]:
    """This Location's categories, most relevant first.

    Ordered by relevance descending then display name, so the ordering is
    stable for equal relevance rather than varying between calls.
    """
    stmt = (
        select(LocationCategoryAssignment, LocationCategory)
        .join(
            LocationCategory,
            LocationCategory.id == LocationCategoryAssignment.category_id,
        )
        .where(LocationCategoryAssignment.location_id == location_id)
        .order_by(
            LocationCategoryAssignment.relevance.desc(),
            LocationCategory.display_name,
        )
    )
    if kind is not None:
        stmt = stmt.where(LocationCategoryAssignment.kind == kind)

    return [
        AssignedCategory(
            kind=assignment.kind,
            slug=category.slug,
            display_name=category.display_name,
            relevance=assignment.relevance,
            confidence=float(assignment.confidence),
            is_primary=assignment.is_primary,
            source=assignment.source,
        )
        for assignment, category in db.execute(stmt).all()
    ]


@dataclass(frozen=True)
class CategorisedLocation:
    """A Location found BY its category, with how relevant that category is
    to it -- so callers can rank 'most wildlife-ish places near here', not
    merely list them."""

    location: Location
    relevance: int
    confidence: float
    distance_meters: float | None


def find_locations_by_category(
    db: Session,
    *,
    slug: str,
    kind: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    radius_meters: float | None = None,
    min_relevance: int = 0,
    limit: int = 20,
) -> list[CategorisedLocation]:
    """Places in a given category, optionally within a radius.

    Geography is done by PostGIS (ST_DWithin / ST_Distance), never by Python
    arithmetic -- the same rule every other distance decision in this codebase
    follows. Ordered by distance when a coordinate is supplied (nearest first,
    which is what a guide wants), by relevance otherwise.
    """
    target = (
        make_point(latitude, longitude)
        if latitude is not None and longitude is not None
        else None
    )
    # Distance is selected in the SAME query rather than looked up per row --
    # an N+1 here would issue one round trip per result.
    distance_column = (
        func.ST_Distance(Location.geog, target) if target is not None else null()
    )

    stmt = (
        select(
            Location,
            LocationCategoryAssignment.relevance,
            LocationCategoryAssignment.confidence,
            distance_column.label("distance_meters"),
        )
        .join(
            LocationCategoryAssignment,
            LocationCategoryAssignment.location_id == Location.id,
        )
        .join(
            LocationCategory,
            LocationCategory.id == LocationCategoryAssignment.category_id,
        )
        .where(
            LocationCategory.slug == slug,
            LocationCategoryAssignment.relevance >= min_relevance,
        )
    )
    if kind is not None:
        stmt = stmt.where(LocationCategory.kind == kind)

    if target is not None:
        if radius_meters is not None:
            stmt = stmt.where(func.ST_DWithin(Location.geog, target, radius_meters))
        stmt = stmt.order_by(func.ST_Distance(Location.geog, target))
    else:
        stmt = stmt.order_by(LocationCategoryAssignment.relevance.desc(), Location.name)

    return [
        CategorisedLocation(
            location=location,
            relevance=relevance,
            confidence=float(confidence),
            distance_meters=float(distance) if distance is not None else None,
        )
        for location, relevance, confidence, distance in db.execute(
            stmt.limit(limit)
        ).all()
    ]


def describe_categories_for_prompt(categories: list[AssignedCategory]) -> str | None:
    """The categories rendered for an LLM prompt, e.g.
    "Temple (place type); Religious 95, Culture & Heritage 90, Historical 70".

    Returns None when there is nothing informative to say, so the caller can
    omit the line entirely rather than print an empty heading -- the same
    "say nothing rather than say nothing meaningfully" rule the rest of the
    prompt builder follows.
    """
    if not categories:
        return None
    place_types = [c for c in categories if c.kind == catalog.KIND_PLACE_TYPE]
    themes = [
        c
        for c in categories
        if c.kind == catalog.KIND_THEME
        and c.slug not in (catalog.OTHER_THEME, catalog.AREA_THEME)
    ]
    parts: list[str] = []
    if place_types:
        parts.append(f"{place_types[0].display_name} (place type)")
    if themes:
        parts.append(
            ", ".join(f"{theme.display_name} {theme.relevance}" for theme in themes)
        )
    if not parts:
        return None
    return "; ".join(parts)
