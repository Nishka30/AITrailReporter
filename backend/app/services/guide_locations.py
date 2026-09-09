import math
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.geo import make_point
from app.db.models.guide import Guide
from app.db.models.guide_location import GuideLocation
from app.schemas.guide_location import GuideLocationCreate


class LocationConflictError(Exception):
    """Raised when a client_location_id is reused with a payload that doesn't match
    the original location sample it was first used for."""

    def __init__(self, existing: GuideLocation):
        self.existing = existing
        super().__init__(
            f"client_location_id {existing.client_location_id!r} was already used "
            "with different location data"
        )


def get_location_by_client_id(db: Session, client_location_id: str) -> GuideLocation | None:
    stmt = select(GuideLocation).where(GuideLocation.client_location_id == client_location_id)
    return db.execute(stmt).scalar_one_or_none()


def _ensure_compatible(existing: GuideLocation, guide_id: UUID, data: GuideLocationCreate) -> None:
    if (
        existing.guide_id != guide_id
        or float(existing.latitude) != data.latitude
        or float(existing.longitude) != data.longitude
        or existing.accuracy_meters != data.accuracy_meters
        or existing.recorded_at != data.recorded_at
    ):
        raise LocationConflictError(existing)


def create_or_get_location(
    db: Session, guide_id: UUID, data: GuideLocationCreate
) -> tuple[GuideLocation, bool]:
    """Create a location sample, or return the existing one if client_location_id
    was already used for an equivalent sample. Raises LocationConflictError if the
    same client_location_id is reused with different data instead of silently
    overwriting the original.

    Race-safe the same way as guides.create_or_get_guide and
    submissions.create_or_get_submission: the DB unique constraint on
    client_location_id is the real guarantee, an IntegrityError on a concurrent
    duplicate insert is caught and resolved by re-fetching the winner's row. When no
    client_location_id is supplied, behaves exactly like the old unconditional
    create_location (always inserts, no idempotency) for backwards compatibility.
    """
    if data.client_location_id is not None:
        existing = get_location_by_client_id(db, data.client_location_id)
        if existing is not None:
            _ensure_compatible(existing, guide_id, data)
            return existing, False

    location = GuideLocation(
        guide_id=guide_id,
        client_location_id=data.client_location_id,
        latitude=data.latitude,
        longitude=data.longitude,
        geog=make_point(data.latitude, data.longitude),
        accuracy_meters=data.accuracy_meters,
        recorded_at=data.recorded_at,
    )
    db.add(location)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if data.client_location_id is not None:
            existing = get_location_by_client_id(db, data.client_location_id)
            if existing is not None:
                _ensure_compatible(existing, guide_id, data)
                return existing, False
        raise
    db.refresh(location)
    return location, True


def get_latest_location(db: Session, guide_id: UUID) -> GuideLocation | None:
    stmt = (
        select(GuideLocation)
        .where(GuideLocation.guide_id == guide_id)
        .order_by(GuideLocation.recorded_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def get_latest_location_at_or_before(
    db: Session, guide_id: UUID, at: datetime
) -> GuideLocation | None:
    """The guide's latest known location recorded at or before `at` (Step 9: used
    to attach the location the guide was actually AT when they made a submission,
    not wherever they happen to be by the time extraction runs). Never returns a
    location recorded AFTER `at` -- if none exists at or before that time, returns
    None rather than fabricating one from a later, closer-but-wrong ping."""
    stmt = (
        select(GuideLocation)
        .where(GuideLocation.guide_id == guide_id, GuideLocation.recorded_at <= at)
        .order_by(GuideLocation.recorded_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def find_nearest_location_in_time(
    db: Session, guide_id: UUID, at: datetime, max_gap: timedelta
) -> tuple[GuideLocation, timedelta] | None:
    """The guide's own recorded GPS sample closest in TIME to `at`, from either
    side, or None if the closest one is further than `max_gap` away.

    WHY BOTH DIRECTIONS, UNLIKE get_latest_location_at_or_before ABOVE: that
    function answers "where was the guide when they made this live report",
    which must never look into the future relative to the report -- a ping
    recorded after submission tells you nothing about where they were AT
    submission. This function answers a different question: "where does the
    guide's OWN GPS history say they probably were at some past moment", for
    content (an old photo, a recalled memory) discovered well after the fact.
    A ping 10 minutes after that moment is exactly as good evidence as one 10
    minutes before -- there is no "future" to protect against once the event
    itself is already in the past relative to now.

    The gap cutoff is the entire safeguard against a wrong answer: a sample
    3 weeks away is not "the guide's location, approximately" -- it is a
    different day's location. Returning None past the cutoff, rather than the
    nearest sample regardless of distance, is what keeps a stale/wrong
    coordinate from ever being asserted as fact (see
    settings.historical_location_max_gap_hours).
    """
    before = db.execute(
        select(GuideLocation)
        .where(GuideLocation.guide_id == guide_id, GuideLocation.recorded_at <= at)
        .order_by(GuideLocation.recorded_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    after = db.execute(
        select(GuideLocation)
        .where(GuideLocation.guide_id == guide_id, GuideLocation.recorded_at > at)
        .order_by(GuideLocation.recorded_at.asc())
        .limit(1)
    ).scalar_one_or_none()

    candidates = [loc for loc in (before, after) if loc is not None]
    if not candidates:
        return None

    best = min(candidates, key=lambda loc: abs(loc.recorded_at - at))
    gap = abs(best.recorded_at - at)
    if gap > max_gap:
        return None
    return best, gap


def list_locations(
    db: Session, guide_id: UUID, limit: int, offset: int
) -> list[GuideLocation]:
    stmt = (
        select(GuideLocation)
        .where(GuideLocation.guide_id == guide_id)
        .order_by(GuideLocation.recorded_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.execute(stmt).scalars().all())


def bounding_box_for_guide(
    db: Session, guide_id: UUID, *, since_days: int | None = 30
) -> tuple[float, float, float, float] | None:
    """The (min_lat, min_lon, max_lat, max_lon) extent of a guide's own
    recorded GPS history, or None if they have none in the window.

    Used ONLY to bias place-autocomplete search results (see
    app/services/places/) toward where this guide has actually been --
    typing "pang" after a Ladakh trip should surface Pangong before some
    unrelated "Pang" on the other side of the world. This is a SOFT bias,
    never a hard filter: a guide is always allowed to describe a memory from
    somewhere they've never recorded a GPS ping.

    `since_days` (default 30) restricts this to RECENT history rather than
    all-time. A guide with two geographically disjoint trips (say, Bengaluru
    months ago and Ladakh now) would otherwise get a bounding box spanning
    both -- its midpoint biases search toward neither real place, which is
    worse than no bias at all. Pass None for all-time (used by callers that
    genuinely want the full history extent, if any emerge later).
    """
    stmt = select(
        func.min(GuideLocation.latitude),
        func.min(GuideLocation.longitude),
        func.max(GuideLocation.latitude),
        func.max(GuideLocation.longitude),
    ).where(GuideLocation.guide_id == guide_id)
    if since_days is not None:
        stmt = stmt.where(GuideLocation.recorded_at >= datetime.now(timezone.utc) - timedelta(days=since_days))
    row = db.execute(stmt).one()
    min_lat, min_lon, max_lat, max_lon = row
    if min_lat is None:
        return None
    return float(min_lat), float(min_lon), float(max_lat), float(max_lon)


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_m = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d_lambda / 2) ** 2
    return 2 * earth_radius_m * math.asin(math.sqrt(a))


def bias_circle_for_bounding_box(
    bounding_box: tuple[float, float, float, float] | None, *, max_radius_meters: float = 50_000.0
) -> tuple[float, float, float] | None:
    """Converts a (min_lat, min_lon, max_lat, max_lon) extent into a
    (center_lat, center_lon, radius_meters) circle, for Google's
    locationBias.circle shape (which has no native bounding-box form, unlike
    Nominatim's viewbox). Radius is the distance to the box's farthest
    corner, capped at `max_radius_meters` (Google's own Nearby/Text Search
    hard limit)."""
    if bounding_box is None:
        return None
    min_lat, min_lon, max_lat, max_lon = bounding_box
    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2
    radius = max(
        _haversine_meters(center_lat, center_lon, min_lat, min_lon),
        _haversine_meters(center_lat, center_lon, min_lat, max_lon),
        _haversine_meters(center_lat, center_lon, max_lat, min_lon),
        _haversine_meters(center_lat, center_lon, max_lat, max_lon),
    )
    # A degenerate box (a guide with exactly one recorded point) collapses to
    # zero radius, which Google's API rejects (radius must be > 0) -- floor
    # it to a sensible minimum "somewhere near this one point" bias instead.
    radius = max(radius, 500.0)
    return center_lat, center_lon, min(radius, max_radius_meters)


def find_nearby_guides(
    db: Session, latitude: float, longitude: float, radius_meters: float
) -> list[dict]:
    """Find active guides whose LATEST known location is within radius_meters of the
    given point. Uses PostGIS (DISTINCT ON for latest-per-guide, ST_DWithin/ST_Distance
    for the spatial filter/ranking) — no distance math happens in Python."""
    target = make_point(latitude, longitude)

    latest_location = (
        select(
            GuideLocation.guide_id,
            GuideLocation.latitude,
            GuideLocation.longitude,
            GuideLocation.geog,
            GuideLocation.recorded_at,
        )
        .distinct(GuideLocation.guide_id)
        .order_by(GuideLocation.guide_id, GuideLocation.recorded_at.desc())
        .subquery()
    )

    distance = func.ST_Distance(latest_location.c.geog, target).label("distance_meters")

    stmt = (
        select(
            Guide.id.label("guide_id"),
            Guide.name,
            Guide.phone_number,
            latest_location.c.latitude,
            latest_location.c.longitude,
            latest_location.c.recorded_at,
            distance,
        )
        .join(latest_location, latest_location.c.guide_id == Guide.id)
        .where(Guide.is_active.is_(True))
        .where(func.ST_DWithin(latest_location.c.geog, target, radius_meters))
        .order_by(distance)
    )

    return [dict(row._mapping) for row in db.execute(stmt).all()]
