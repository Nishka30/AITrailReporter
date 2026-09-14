"""Classifying Locations that already exist, and the model sweep for the
ones rules could not describe.

TWO DISTINCT PASSES, deliberately separable:

  backfill_deterministic() -- free, offline, idempotent. Classifies every
      Location from what it already stores. Safe to run repeatedly and safe
      to run over the whole table; no network, no spend.

  sweep_ai_classifications() -- costs real model calls, so it is explicitly
      opt-in (settings.location_category_ai_enabled), hard-capped per run
      (settings.location_category_ai_max_per_run), and only ever touches
      places the deterministic pass genuinely could not describe.

Running the free pass first and the paid pass only over its leftovers is the
entire cost-control design: on real data the large majority of places
classify from Google's own types for nothing.
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.location import Location
from app.db.models.location_category import LocationCategoryAssignment
from app.services.places import category_ai, category_assignment, category_rules

logger = logging.getLogger(__name__)


class BackfillStats:
    def __init__(self) -> None:
        self.considered = 0
        self.classified = 0
        # Places the RULES alone could not describe. Deliberately not called
        # "still weak": a place already described by an earlier model pass
        # counts here (rules still cannot describe it) while no longer being
        # a candidate for another one. What the next AI sweep would actually
        # cost is _weak_location_ids, which reads persisted state.
        self.rules_insufficient = 0
        self.failed = 0

    def __str__(self) -> str:
        return (
            f"considered={self.considered} classified={self.classified} "
            f"rules_insufficient={self.rules_insufficient} failed={self.failed}"
        )


class AiSweepStats:
    def __init__(self) -> None:
        self.candidates = 0
        self.attempted = 0
        self.succeeded = 0
        self.failed = 0
        self.skipped_disabled = False

    def __str__(self) -> str:
        if self.skipped_disabled:
            return "skipped: location_category_ai_enabled is false"
        return (
            f"candidates={self.candidates} attempted={self.attempted} "
            f"succeeded={self.succeeded} failed={self.failed}"
        )


def backfill_deterministic(db: Session, *, limit: int | None = None) -> BackfillStats:
    """Run rule-based classification over every Location.

    Per-Location savepoints so one bad row cannot roll back the batch -- the
    same pattern seed_import.run_full_import uses. Commits once at the end.
    """
    stats = BackfillStats()
    stmt = select(Location).order_by(Location.created_at)
    if limit is not None:
        stmt = stmt.limit(limit)

    for location in db.execute(stmt).scalars().all():
        stats.considered += 1
        try:
            with db.begin_nested():
                proposals = category_assignment.proposals_for_location(location)
                category_assignment.assign_categories(
                    db, location, proposals=proposals
                )
                if category_rules.is_weak(proposals):
                    stats.rules_insufficient += 1
                else:
                    stats.classified += 1
        except Exception as exc:  # noqa: BLE001 -- one row must not kill the run
            stats.failed += 1
            logger.warning(
                "Backfill failed for %r: %s", location.name, type(exc).__name__
            )
    db.commit()
    return stats


def _weak_location_ids(db: Session, limit: int) -> list:
    """Locations the model fallback should be spent on.

    Exactly category_rules.is_weak, expressed against what was actually
    PERSISTED rather than by re-running the rules over every row: a place is
    weak if it has fewer than MIN_INFORMATIVE_THEMES theme assignments that
    say something, where 'other' and 'area' say nothing.

    The two definitions MUST stay in step, which is why this mirrors the
    single theme-count test rather than adding a place_type clause of its
    own. A place_type-based test would re-select an area every sweep even
    after the model had described it perfectly well, paying again for the
    same answer each time.
    """
    from app.db.models.location_category import LocationCategory

    informative_themes = (
        select(
            LocationCategoryAssignment.location_id.label("location_id"),
            func.count().label("theme_count"),
        )
        .join(
            LocationCategory,
            LocationCategory.id == LocationCategoryAssignment.category_id,
        )
        .where(
            LocationCategoryAssignment.kind == "theme",
            LocationCategory.slug.notin_(["other", "area"]),
        )
        .group_by(LocationCategoryAssignment.location_id)
        .subquery()
    )

    stmt = (
        select(Location.id)
        .outerjoin(
            informative_themes, informative_themes.c.location_id == Location.id
        )
        .where(
            func.coalesce(informative_themes.c.theme_count, 0)
            < category_rules.MIN_INFORMATIVE_THEMES
        )
        .order_by(Location.created_at)
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


def sweep_ai_classifications(db: Session, *, limit: int | None = None) -> AiSweepStats:
    """Ask the model about places the rules could not describe.

    Each classification is committed on its own so a failure partway through
    a sweep keeps the work already paid for. Never raises: a model outage
    leaves places with their rule-based categories, which is a worse answer
    than the model would give but a perfectly usable one.
    """
    stats = AiSweepStats()
    if not settings.location_category_ai_enabled:
        stats.skipped_disabled = True
        return stats

    cap = limit if limit is not None else settings.location_category_ai_max_per_run
    location_ids = _weak_location_ids(db, cap)
    stats.candidates = len(location_ids)

    for location_id in location_ids:
        location = db.get(Location, location_id)
        if location is None:
            continue
        stats.attempted += 1
        try:
            proposals = category_ai.classify_with_model(
                name=location.name,
                locality=location.locality,
                formatted_address=location.formatted_address,
                google_primary_type=location.google_primary_type,
                google_types=location.google_types,
                description=location.description,
                place_kind=location.place_kind,
            )
            category_assignment.assign_categories(db, location, proposals=proposals)
            db.commit()
            stats.succeeded += 1
            logger.info("AI-classified %r.", location.name)
        except Exception as exc:  # noqa: BLE001 -- deliberate best-effort boundary
            db.rollback()
            stats.failed += 1
            logger.warning(
                "AI classification failed for %r: %s",
                location.name,
                type(exc).__name__,
            )
    return stats
