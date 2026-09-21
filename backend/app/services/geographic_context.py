from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.schemas.geographic_context import GeographicContext, NearestKnownPlace
from app.services import locations as location_service


def resolve_geographic_context(
    db: Session, latitude: float, longitude: float
) -> GeographicContext:
    """Resolve a raw coordinate into geographic context: the nearest known place,
    if any known place falls within GEOGRAPHIC_CONTEXT_RADIUS_METERS. A place is
    only attached when it's actually within that radius — never "nearest regardless
    of distance"."""
    nearest = location_service.find_nearest_location(
        db, latitude, longitude, settings.geographic_context_radius_meters
    )
    nearest_known_place = (
        NearestKnownPlace(
            id=nearest["id"],
            name=nearest["name"],
            distance_meters=nearest["distance_meters"],
        )
        if nearest is not None
        else None
    )
    return GeographicContext(
        latitude=latitude,
        longitude=longitude,
        nearest_known_place=nearest_known_place,
    )


def batch_nearest_known_places(
    db: Session,
    points: dict[UUID, tuple[float, float]],
    radius_meters: float | None = None,
) -> dict[UUID, NearestKnownPlace]:
    """The SAME "nearest known Location within radius" resolution as
    resolve_geographic_context above, but for a whole PAGE of coordinates in
    ONE round trip instead of one PostGIS query per row.

    THIS is what makes it safe for a paginated admin list to show a "Near
    <place>" caption without reintroducing the N+1 pattern that was
    deliberately removed from list_review_queue/list_contribution_queue: a
    page of 25 rows costs exactly one query here, not 25 -- see this
    module's own resolve_geographic_context for the per-row version, still
    used (deliberately) by single-item detail reads, where one extra query
    is genuinely cheap.

    `points` maps an arbitrary caller-chosen key (a submission_id or
    observation_id) to (latitude, longitude). Returns only the keys that
    had a match within radius -- a key with nothing nearby is simply absent
    from the result, exactly mirroring resolve_geographic_context returning
    nearest_known_place=None. This is enrichment metadata about a KNOWN
    Location possibly being nearby; it must never be read as, or used to
    decide, whether the underlying contribution itself has a location --
    that question is answered entirely by the coordinate the caller already
    has, before this function is ever called.

    Implemented as a single LATERAL join (one nearest-Location lookup PER
    input point, computed by the database in one query) rather than N
    separate resolve_geographic_context calls -- see the query below.
    """
    if not points:
        return {}
    radius = radius_meters if radius_meters is not None else settings.geographic_context_radius_meters
    keys = [str(k) for k in points]
    lats = [float(v[0]) for v in points.values()]
    lons = [float(v[1]) for v in points.values()]

    stmt = text(
        """
        WITH pts AS (
            SELECT * FROM unnest(
                CAST(:keys AS text[]), CAST(:lats AS float8[]), CAST(:lons AS float8[])
            ) AS t(key, lat, lon)
        )
        SELECT pts.key, nearest.id, nearest.name, nearest.distance_meters
        FROM pts
        LEFT JOIN LATERAL (
            SELECT l.id, l.name,
                   ST_Distance(l.geog, ST_SetSRID(ST_MakePoint(pts.lon, pts.lat), 4326)::geography)
                       AS distance_meters
            FROM locations l
            WHERE ST_DWithin(
                l.geog, ST_SetSRID(ST_MakePoint(pts.lon, pts.lat), 4326)::geography, :radius
            )
            ORDER BY distance_meters
            LIMIT 1
        ) nearest ON true
        """
    )
    rows = db.execute(stmt, {"keys": keys, "lats": lats, "lons": lons, "radius": radius}).all()

    result: dict[UUID, NearestKnownPlace] = {}
    for key, location_id, name, distance_meters in rows:
        if location_id is not None:
            result[UUID(key)] = NearestKnownPlace(
                id=location_id, name=name, distance_meters=float(distance_meters)
            )
    return result
