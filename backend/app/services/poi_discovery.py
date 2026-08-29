"""POI discovery: turning a bare coordinate into real, named Locations.

WHY THIS EXISTS
Everything place-specific in this system hangs off the `locations` table. A
guide's GPS only becomes "you're at Hillary Bridge" because a Location row sits
within `geographic_context_radius_meters` of them. With an empty table --
which is exactly what production had -- `geographic_context` resolves nothing,
place research never runs, no "you're here" invitations exist, and Explore
falls back to generic prompts however good the downstream prompts are. The
pipeline was never broken; it was starving.

This module feeds it, from real map data rather than curation.

Two sources, split by what each is genuinely authoritative about:

    OpenStreetMap  ->  what exists here, and exactly where     (facts)
    Claude         ->  which of those are worth asking about   (judgement)

So a discovered place can never be a place that does not exist, and can never
be in a position nobody published -- that is structural here, not a rule the
prompt asks a model to follow.

Concurrency follows the established pattern from extractions.py /
place_questions.py: the discovery row is claimed under SELECT ... FOR UPDATE
and the lock is RELEASED BEFORE the external call -- a slow network call must
never hold a database row lock.

Nothing here touches the knowledge-gap pipeline. It creates Locations; the
existing services take it from there entirely unmodified.
"""

import logging
import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.geo import make_point
from app.db.models.location import Location
from app.db.models.poi_discovery import PoiDiscovery
from app.services.poi_discovery_research import osm_provider, selection

logger = logging.getLogger(__name__)


def cell_key_for(latitude: float, longitude: float) -> str:
    """The discovery grid cell containing this coordinate.

    Rounding to `poi_discovery_cell_degrees` (0.01 deg, ~1.1km) is what makes
    discovery cacheable at all. Keyed on raw coordinates, the metre-scale
    jitter of a stationary phone would look like an endless stream of new
    places to research, re-paying for the same web searches forever. Keyed on a
    cell, a neighbourhood is researched once and every guide who passes through
    afterwards is served from that one run.

    Deterministic and dependency-free: the same coordinate always yields the
    same key, which is what the UNIQUE constraint on the table relies on.
    """
    step = settings.poi_discovery_cell_degrees
    lat_cell = math.floor(latitude / step) * step
    lon_cell = math.floor(longitude / step) * step
    return f"{lat_cell:.4f},{lon_cell:.4f}"


def cell_center(cell_key: str) -> tuple[float, float]:
    """The centre of a cell, which is what actually gets searched -- never the
    guide's exact position. This keeps a person's precise location out of an
    outbound request and out of this table."""
    lat_s, lon_s = cell_key.split(",")
    step = settings.poi_discovery_cell_degrees
    return float(lat_s) + step / 2, float(lon_s) + step / 2


def get_discovery(db: Session, cell_key: str) -> PoiDiscovery | None:
    stmt = select(PoiDiscovery).where(PoiDiscovery.cell_key == cell_key)
    return db.execute(stmt).scalar_one_or_none()


def is_abandoned(discovery: PoiDiscovery) -> bool:
    """True when a run claims to be 'processing' but cannot still be running.

    WHY THIS IS NECESSARY: the claim below refuses to start a second run while
    one is already 'processing', which is correct -- it stops two guides in the
    same neighbourhood both paying for the same web searches. But nothing
    resets that flag if the process holding it dies: a crash, a container
    restart, a deploy mid-run, or an OOM kill all leave the row stuck. Without
    recovery, that cell is locked out of discovery PERMANENTLY, and the failure
    is invisible -- the app just quietly never gets places there again.

    The cutoff is this run's OWN worst case -- both external calls timing out
    back to back -- plus a margin. Past that point the original attempt has
    either finished (and would have moved the status) or can no longer be
    alive, so reclaiming is safe rather than a race.
    """
    if discovery.status != "processing":
        return False
    started = discovery.started_at
    if started is None:
        # 'processing' with no start time is incoherent state; reclaim it.
        return True
    cutoff = (
        settings.osm_request_timeout_seconds
        + settings.anthropic_request_timeout_seconds
        + 120
    )
    age = datetime.now(timezone.utc) - started
    return age.total_seconds() > cutoff


def is_discovery_stale(discovery: PoiDiscovery | None) -> bool:
    """True when a (re)discovery is due: never run, or the last SUCCESSFUL run
    is older than the configured window. A row stuck in 'failed' with no
    discovered_at is stale, so retries remain possible -- but a row currently
    'processing' is NOT restarted here (see ensure_discovered)."""
    if discovery is None or discovery.discovered_at is None:
        return True
    age = datetime.now(timezone.utc) - discovery.discovered_at
    return age > timedelta(days=settings.poi_discovery_refresh_days)


def _ensure_discovery_row(db: Session, cell_key: str) -> PoiDiscovery:
    """Get-or-create, race-safe via the UNIQUE constraint on cell_key -- the
    same IntegrityError-catch-and-refetch pattern used elsewhere, because an
    INSERT race cannot be solved with SELECT FOR UPDATE (there is no row to
    lock yet)."""
    existing = get_discovery(db, cell_key)
    if existing is not None:
        return existing
    lat, lon = cell_center(cell_key)
    discovery = PoiDiscovery(
        cell_key=cell_key, center_latitude=lat, center_longitude=lon, status="pending"
    )
    db.add(discovery)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = get_discovery(db, cell_key)
        if existing is None:
            raise
        return existing
    return discovery


def _distance_meters(db: Session, lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    """Great-circle distance via PostGIS, not Python trigonometry -- the same
    geography type and the same ST_Distance the rest of the system uses, so
    'near' means exactly the same thing here as it does everywhere else."""
    return float(
        db.execute(
            select(func.ST_Distance(make_point(lat_a, lon_a), make_point(lat_b, lon_b)))
        ).scalar_one()
    )


def _existing_nearby_place(db: Session, latitude: float, longitude: float) -> Location | None:
    """An already-known place within the dedup radius, if any.

    Dedup is GEOGRAPHIC, not by name: the same bridge legitimately appears as
    "Hillary Bridge", "Hillary Suspension Bridge" and "Edmund Hillary Bridge"
    across different sources, and string matching would store three anchors for
    one physical thing. Two places within a few tens of metres are treated as
    one, which is also how a guide standing there would see it.
    """
    target = make_point(latitude, longitude)
    stmt = (
        select(Location)
        .where(func.ST_DWithin(Location.geog, target, settings.poi_discovery_dedup_radius_meters))
        .order_by(func.ST_Distance(Location.geog, target))
        .limit(1)
    )
    return db.execute(stmt).scalars().first()


def _persist_places(
    db: Session,
    cell_key: str,
    center_lat: float,
    center_lon: float,
    chosen: list[tuple[osm_provider.OsmPlace, str]],
) -> int:
    """Creates Location rows for genuinely new places.

    Names and coordinates here came from OpenStreetMap, so there is no question
    of an invented landmark or an invented position -- that is the whole reason
    discovery is built this way (see osm_provider's header). The distance check
    below is therefore a sanity check on OUR OWN query construction, not a
    hallucination guard: if a place comes back further from the cell centre than
    we asked for, the radius maths is wrong somewhere and the row is skipped
    rather than trusted.

    Geographic dedup still matters, because OSM legitimately holds the same
    feature more than once (a temple as both a node and its enclosing way) and
    because a neighbouring cell may already have stored it.
    """
    kept = 0
    for place, reason in chosen:
        if kept >= settings.poi_discovery_max_places:
            break

        distance = _distance_meters(db, center_lat, center_lon, place.latitude, place.longitude)
        if distance > settings.poi_discovery_accept_radius_meters:
            logger.info(
                "Skipped %r: %.0fm from cell centre (max %dm).",
                place.name,
                distance,
                settings.poi_discovery_accept_radius_meters,
            )
            continue

        duplicate = _existing_nearby_place(db, place.latitude, place.longitude)
        if duplicate is not None:
            logger.info("Skipped %r: already known as %r.", place.name, duplicate.name)
            continue

        db.add(
            Location(
                name=place.name,
                # The model's one-line description when it supplied one,
                # otherwise the plain OSM kind. Never left to imply more than
                # is actually known about the place.
                description=reason or f"A {place.place_kind} near here.",
                latitude=place.latitude,
                longitude=place.longitude,
                geog=make_point(place.latitude, place.longitude),
                source="discovered",
                place_kind=place.place_kind or None,
                # A real, checkable citation: the OSM object itself.
                source_urls=[place.source_url],
                discovery_cell_key=cell_key,
            )
        )
        # Flushed per place so the NEXT iteration's dedup query can see it --
        # otherwise one batch could store the same feature twice.
        db.flush()
        kept += 1
    return kept


def ensure_discovered(db: Session, latitude: float, longitude: float, force: bool = False) -> PoiDiscovery:
    """Discovers real places around a coordinate if due (or if forced).

    Returns the discovery row in its resulting state. A 'failed' outcome is a
    legitimate, honest result -- callers should carry on with whatever places
    already exist rather than erroring.
    """
    cell_key = cell_key_for(latitude, longitude)
    center_lat, center_lon = cell_center(cell_key)

    discovery = _ensure_discovery_row(db, cell_key)
    db.commit()

    locked = db.execute(
        select(PoiDiscovery).where(PoiDiscovery.id == discovery.id).with_for_update()
    ).scalar_one()

    if locked.status == "processing" and not is_abandoned(locked):
        # Another request is genuinely still researching this cell. Don't
        # duplicate the web spend; the caller serves whatever exists meanwhile.
        db.commit()
        return locked

    if is_abandoned(locked):
        # A previous attempt died holding the claim (crash, restart, deploy).
        # Logged rather than silently reclaimed: repeated reclaims of the same
        # cell mean runs are dying, which is worth noticing.
        logger.warning(
            "Reclaiming abandoned POI discovery for cell %s (started %s).",
            cell_key,
            locked.started_at,
        )

    if not force and not is_discovery_stale(locked):
        db.commit()
        return locked

    locked.status = "processing"
    locked.attempt_count += 1
    locked.started_at = datetime.now(timezone.utc)
    locked.error_message = None
    # Provenance recorded as it actually is: the places themselves come from
    # OpenStreetMap, and the model only filters them. The column's historic
    # default of 'anthropic' would misreport where this data originated.
    locked.provider = "openstreetmap"
    locked.model = settings.anthropic_model
    # Releases the row lock BEFORE the external call.
    db.commit()

    try:
        # 1. FACTS: what actually exists here, and exactly where. From
        #    OpenStreetMap, so no name or coordinate is ever model-generated.
        candidates = osm_provider.fetch_places(
            center_lat,
            center_lon,
            settings.poi_discovery_search_radius_meters,
            settings.poi_discovery_candidate_limit,
        )
    except osm_provider.OsmProviderError as exc:
        failed = db.get(PoiDiscovery, discovery.id)
        failed.status = "failed"
        failed.error_message = str(getattr(exc, "message", exc))[:500]
        failed.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.warning("POI discovery failed for cell %s: %s", cell_key, type(exc).__name__)
        return failed

    # 2. JUDGEMENT: which of those real places are worth anchoring an
    #    experience to. Best-effort and never raises -- if selection is
    #    unavailable the OSM list is kept unfiltered, which is far better than
    #    discovering nothing (see selection.select_places).
    chosen = selection.select_places(candidates, settings.poi_discovery_max_places)

    kept = _persist_places(db, cell_key, center_lat, center_lon, chosen)

    done = db.get(PoiDiscovery, discovery.id)
    done.status = "completed"
    done.error_message = None
    completed_at = datetime.now(timezone.utc)
    done.completed_at = completed_at
    # Only a SUCCESSFUL run moves discovered_at, so repeated failures can never
    # masquerade as fresh coverage and suppress future attempts.
    done.discovered_at = completed_at
    done.discovered_count = kept
    db.commit()

    logger.info("Discovered %d place(s) for cell %s.", kept, cell_key)
    return done


def maybe_ensure_discovered(db: Session, latitude: float, longitude: float) -> None:
    """Best-effort trigger. Never raises: a discovery failure must not break
    whatever the caller was actually doing. Mirrors
    place_questions.maybe_ensure_researched's swallow-everything contract."""
    try:
        ensure_discovered(db, latitude, longitude)
    except Exception as exc:  # noqa: BLE001 -- deliberate best-effort boundary
        logger.warning(
            "Best-effort POI discovery failed for %.5f,%.5f: %s",
            latitude,
            longitude,
            type(exc).__name__,
        )
