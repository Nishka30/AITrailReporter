"""Seeds example Route/RouteStop rows from EXISTING Location rows -- proof
that the Route/RouteStop model (app/db/models/route.py) is genuinely
reusable, not Everest-specific application logic. The stop lists below are
plain data; nothing about the model, this script's own machinery, or the
frontend RouteStrip component depends on which route is seeded.

Run manually, after the routes/route_stops migration has been applied:

    python scripts/seed_routes.py

Idempotent: re-running reconciles each route's stops in place (get-or-create
by slug/by (route_id, location_id), updating sequence_order/elevation_meters/
stop_label). NEVER creates a Location -- a named stop with no matching
Location yet in this database is logged and skipped, not fabricated. Gaps in
sequence_order from a skipped stop are fine; RouteStop's own
uq_route_stops_route_sequence_order constraint is per-route, not
contiguous-only.
"""

import logging
import pathlib
import sys
from dataclasses import dataclass

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.geo import make_point
from app.db.models.location import Location
from app.db.models.route import Route, RouteStop
from app.db.session import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("seed_routes")

# Narrows the by-name lookup to the right real-world place among possible
# name collisions elsewhere in the world. NEVER used to create a Location --
# a miss here is a skip, never a fallback to creating one.
_STOP_SEARCH_RADIUS_METERS = 5_000


@dataclass(frozen=True)
class _StopSeed:
    name: str
    latitude: float
    longitude: float
    sequence_order: int
    elevation_meters: int | None = None
    stop_label: str | None = None


@dataclass(frozen=True)
class _RouteSeed:
    slug: str
    name: str
    description: str | None
    stops: tuple[_StopSeed, ...]


EVEREST_BASE_CAMP_ROUTE = _RouteSeed(
    slug="everest-base-camp-trek",
    name="Everest Base Camp Trek",
    description=(
        "The classic multi-day trek through the Khumbu region, from Lukla's "
        "airstrip up to Everest Base Camp itself."
    ),
    stops=(
        _StopSeed("Lukla", 27.6869, 86.7297, 1, elevation_meters=2860),
        _StopSeed("Phakding", 27.7486, 86.7128, 2, elevation_meters=2610),
        _StopSeed("Namche Bazaar", 27.8069, 86.7139, 3, elevation_meters=3440),
        _StopSeed("Tengboche", 27.8360, 86.7638, 4, elevation_meters=3860, stop_label="Monastery stop"),
        _StopSeed("Dingboche", 27.8913, 86.8300, 5, elevation_meters=4410),
        _StopSeed("Lobuche", 27.9611, 86.8078, 6, elevation_meters=4940),
        _StopSeed("Gorak Shep", 27.9819, 86.8281, 7, elevation_meters=5164),
        _StopSeed("Everest Base Camp", 28.0026, 86.8528, 8, elevation_meters=5364),
    ),
)

# Add future routes here -- each one just another plain _RouteSeed.
ROUTE_SEEDS: tuple[_RouteSeed, ...] = (EVEREST_BASE_CAMP_ROUTE,)


def _find_location_by_name(db: Session, name: str, latitude: float, longitude: float) -> Location | None:
    target = make_point(latitude, longitude)
    stmt = (
        select(Location)
        .where(func.lower(Location.name) == name.lower())
        .where(func.ST_DWithin(Location.geog, target, _STOP_SEARCH_RADIUS_METERS))
        .order_by(func.ST_Distance(Location.geog, target))
        .limit(1)
    )
    return db.execute(stmt).scalars().first()


def _ensure_route(db: Session, seed: _RouteSeed) -> Route:
    route = db.execute(select(Route).where(Route.slug == seed.slug)).scalars().first()
    if route is None:
        route = Route(slug=seed.slug, name=seed.name, description=seed.description)
        db.add(route)
        db.flush()
        logger.info("Created route %r (%s)", seed.name, seed.slug)
    else:
        route.name = seed.name
        route.description = seed.description
    return route


def _ensure_stop(db: Session, route: Route, location: Location, stop: _StopSeed) -> None:
    existing = db.execute(
        select(RouteStop).where(RouteStop.route_id == route.id, RouteStop.location_id == location.id)
    ).scalars().first()
    if existing is None:
        db.add(
            RouteStop(
                route_id=route.id,
                location_id=location.id,
                sequence_order=stop.sequence_order,
                stop_label=stop.stop_label,
                elevation_meters=stop.elevation_meters,
            )
        )
        logger.info("  + stop %d: %s -> Location %s", stop.sequence_order, stop.name, location.id)
    else:
        existing.sequence_order = stop.sequence_order
        existing.stop_label = stop.stop_label
        existing.elevation_meters = stop.elevation_meters
        logger.info("  = stop %d: %s (already on route)", stop.sequence_order, stop.name)


def seed_route(db: Session, seed: _RouteSeed) -> None:
    logger.info("Seeding route %r", seed.name)
    route = _ensure_route(db, seed)

    resolved = 0
    for stop in seed.stops:
        location = _find_location_by_name(db, stop.name, stop.latitude, stop.longitude)
        if location is None:
            logger.warning(
                "  - stop %d: %r has no matching Location yet within %dm -- skipped, not created.",
                stop.sequence_order,
                stop.name,
                _STOP_SEARCH_RADIUS_METERS,
            )
            continue
        _ensure_stop(db, route, location, stop)
        resolved += 1

    logger.info("Route %r: %d/%d stops resolved.", seed.name, resolved, len(seed.stops))


def main() -> None:
    db = SessionLocal()
    try:
        for seed in ROUTE_SEEDS:
            seed_route(db, seed)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
