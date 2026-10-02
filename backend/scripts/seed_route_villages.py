"""Adds the real Everest Base Camp villages as Locations, so the route seeded
by scripts/seed_routes.py resolves every stop. Real geography only: names and
coordinates come straight from seed_routes.EVEREST_BASE_CAMP_ROUTE, and each
village gets a short factual description and catalog categories. No guides,
reports or answers -- safe for production.

Dry run by default (prints what it would do). To write, pass --apply AND
--confirm-host with the hostname of the database you are connected to:

    python scripts/seed_route_villages.py
    python scripts/seed_route_villages.py --apply --confirm-host localhost

Idempotent: a village that already exists (same name within 5 km) is left
untouched, and the route is re-seeded in place.
"""

import argparse
import logging
import pathlib
import sys
from dataclasses import dataclass
from urllib.parse import urlsplit

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.geo import make_point
from app.db.models.location import Location
from app.db.models.location_category import LocationCategory, LocationCategoryAssignment
from app.db.session import SessionLocal

import seed_routes  # noqa: E402  (scripts/ is on sys.path when run directly)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("seed_route_villages")

ROUTE_VILLAGE_PROVIDER = "route_seed"
_EXISTING_MATCH_RADIUS_METERS = 5_000


@dataclass(frozen=True)
class Village:
    name: str
    description: str
    place_type: str
    themes: tuple[str, ...]


VILLAGES = (
    Village(
        "Phakding",
        "A riverside village on the Dudh Koshi and the usual first overnight after flying into Lukla, "
        "with lodges strung along both banks.",
        "area",
        ("trekking", "lodging", "nature"),
    ),
    Village(
        "Namche Bazaar",
        "The Sherpa trading town of the Khumbu, built in a horseshoe on the hillside, and the main "
        "acclimatisation stop on the way to base camp.",
        "area",
        ("trekking", "lodging", "local_life", "food_drink"),
    ),
    Village(
        "Tengboche",
        "A ridge-top village around Tengboche Monastery, the largest gompa in the Khumbu, with wide "
        "views of Ama Dablam and Everest.",
        "monastery",
        ("culture_heritage", "religious", "trekking", "lodging"),
    ),
    Village(
        "Dingboche",
        "A stone-walled farming village below Ama Dablam where most itineraries spend a second "
        "acclimatisation day.",
        "area",
        ("trekking", "lodging", "nature"),
    ),
    Village(
        "Lobuche",
        "A small cluster of lodges beside the Khumbu Glacier moraine, the last overnight before Gorak Shep.",
        "area",
        ("trekking", "lodging", "adventure"),
    ),
    Village(
        "Gorak Shep",
        "The last lodge settlement below Everest Base Camp, on a frozen lakebed at about 5,160 m.",
        "area",
        ("trekking", "lodging", "adventure"),
    ),
    Village(
        "Everest Base Camp",
        "The climbers' camp on the Khumbu Glacier at about 5,364 m, reached as a day walk from Gorak Shep.",
        "base_camp",
        ("trekking", "adventure", "nature", "scenic_spot"),
    ),
)


def database_host() -> str | None:
    return urlsplit(settings.database_url.replace("+psycopg", "")).hostname


def _category(db: Session, slug: str, kind: str) -> LocationCategory:
    category = db.execute(
        select(LocationCategory).where(LocationCategory.slug == slug, LocationCategory.kind == kind)
    ).scalars().first()
    if category is None:
        raise SystemExit(f"Catalog category {slug!r} ({kind}) not found -- aborting before any write")
    return category


def _assign(db: Session, location: Location, slug: str, kind: str, relevance: int, primary: bool, rationale: str) -> LocationCategoryAssignment:
    category = _category(db, slug, kind)
    existing = db.execute(
        select(LocationCategoryAssignment).where(
            LocationCategoryAssignment.location_id == location.id,
            LocationCategoryAssignment.category_id == category.id,
        )
    ).scalars().first()
    if existing is not None:
        return existing
    assignment = LocationCategoryAssignment(
        location_id=location.id,
        category_id=category.id,
        kind=kind,
        relevance=relevance,
        confidence=0.9,
        is_primary=primary,
        source="manual",
        rationale=rationale,
    )
    db.add(assignment)
    db.flush()
    return assignment


def _existing(db: Session, name: str, latitude: float, longitude: float) -> Location | None:
    target = make_point(latitude, longitude)
    return db.execute(
        select(Location)
        .where(func.lower(Location.name) == name.lower())
        .where(func.ST_DWithin(Location.geog, target, _EXISTING_MATCH_RADIUS_METERS))
        .limit(1)
    ).scalars().first()


def seed_villages(db: Session, provider: str = ROUTE_VILLAGE_PROVIDER, rationale: str = "route village seed") -> int:
    """Creates the missing villages and re-seeds the route. Returns how many
    villages were created. Never modifies a village that already exists."""
    for village in VILLAGES:  # validate the whole catalog before writing anything
        _category(db, village.place_type, "place_type")
        for theme in village.themes:
            _category(db, theme, "theme")

    by_name = {s.name: s for s in seed_routes.EVEREST_BASE_CAMP_ROUTE.stops}
    created = 0
    for village in VILLAGES:
        stop = by_name[village.name]
        if _existing(db, village.name, stop.latitude, stop.longitude) is not None:
            logger.info("= %s already exists -- left untouched", village.name)
            continue
        location = Location(
            name=village.name,
            description=village.description,
            latitude=stop.latitude,
            longitude=stop.longitude,
            geog=make_point(stop.latitude, stop.longitude),
            source="manual",
            provider=provider,
            locality="Khumbu, Solukhumbu",
        )
        db.add(location)
        db.flush()
        _assign(db, location, village.place_type, "place_type", 100, True, rationale)
        for i, theme in enumerate(village.themes):
            _assign(db, location, theme, "theme", 90 - i * 8, False, rationale)
        created += 1
        logger.info("+ %s (%.4f, %.4f)", village.name, stop.latitude, stop.longitude)
    seed_routes.seed_route(db, seed_routes.EVEREST_BASE_CAMP_ROUTE)
    return created


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write the changes (default is a dry run).")
    parser.add_argument("--confirm-host", help="Must equal the connected database's hostname when --apply is set.")
    args = parser.parse_args()

    host = database_host()
    logger.info("Environment: %s · database host: %s", settings.app_environment, host)
    if args.apply and args.confirm_host != host:
        raise SystemExit(f"--confirm-host must be {host!r} to write to this database. Nothing was changed.")

    db = SessionLocal()
    try:
        created = seed_villages(db)
        if args.apply:
            db.commit()
            logger.info("Committed: %d village(s) created.", created)
        else:
            db.rollback()
            logger.info("Dry run: %d village(s) would be created. Re-run with --apply --confirm-host %s to write.", created, host)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
