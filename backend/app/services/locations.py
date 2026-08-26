from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.geo import make_point
from app.db.models.location import Location
from app.schemas.location import LocationCreate


def create_location(db: Session, data: LocationCreate) -> Location:
    location = Location(
        name=data.name,
        description=data.description,
        latitude=data.latitude,
        longitude=data.longitude,
        geog=make_point(data.latitude, data.longitude),
    )
    db.add(location)
    db.commit()
    db.refresh(location)
    return location


def get_location(db: Session, location_id: UUID) -> Location | None:
    return db.get(Location, location_id)


def find_nearby_locations(
    db: Session, latitude: float, longitude: float, radius_meters: float
) -> list[dict]:
    """Known places within radius_meters of the given point, nearest first. Uses
    PostGIS (ST_DWithin/ST_Distance) for filtering and distance — not Python math."""
    target = make_point(latitude, longitude)
    distance = func.ST_Distance(Location.geog, target).label("distance_meters")

    stmt = (
        select(
            Location.id,
            Location.name,
            Location.description,
            Location.latitude,
            Location.longitude,
            distance,
        )
        .where(func.ST_DWithin(Location.geog, target, radius_meters))
        .order_by(distance)
    )
    return [dict(row._mapping) for row in db.execute(stmt).all()]


def find_nearest_location(
    db: Session, latitude: float, longitude: float, radius_meters: float
) -> dict | None:
    """The single nearest known place within radius_meters, or None if none qualify."""
    target = make_point(latitude, longitude)
    distance = func.ST_Distance(Location.geog, target).label("distance_meters")

    stmt = (
        select(Location.id, Location.name, distance)
        .where(func.ST_DWithin(Location.geog, target, radius_meters))
        .order_by(distance)
        .limit(1)
    )
    row = db.execute(stmt).first()
    return dict(row._mapping) if row is not None else None
