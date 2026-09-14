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

    Google Places  ->  what exists here, and exactly where     (facts)
    categories.py  ->  what TrailMind calls it                 (deterministic)

So a discovered place can never be a place that does not exist, and can never
be in a position nobody published -- that is structural here, not a rule a
model is asked to follow. (An earlier version of this module also ran a
Claude "worth keeping" judgement pass over OSM candidates; Google Places'
typed, allowlisted results do that filtering job now, so that extra model
call is gone -- see categories.NEARBY_SEARCH_INCLUDED_TYPES.)

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

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.geo import make_point
from app.db.models.location import Location
from app.db.models.poi_discovery import PoiDiscovery
from app.services import locations as location_service
from app.services.places import categories
from app.services.places.base import DiscoveredPlace, PlaceProviderError
from app.services.places.google_provider import PROVIDER_NAME, get_place_provider

logger = logging.getLogger(__name__)


def cell_key_for(latitude: float, longitude: float) -> str:
    """The discovery grid cell containing this coordinate.

    Rounding to `poi_discovery_cell_degrees` (0.01 deg, ~1.1km) is what makes
    discovery cacheable at all -- and, with a real per-request price on
    Google's Nearby Search, cost-controlled. Keyed on raw coordinates, the
    metre-scale jitter of a stationary phone would look like an endless
    stream of new places to research, re-paying for the same search forever.
    Keyed on a cell, a neighbourhood is researched once and every guide who
    passes through afterwards is served from that one run.

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
    same neighbourhood both paying for the same search. But nothing resets
    that flag if the process holding it dies: a crash, a container restart, a
    deploy mid-run, or an OOM kill all leave the row stuck. Without recovery,
    that cell is locked out of discovery PERMANENTLY, and the failure is
    invisible -- the app just quietly never gets places there again.

    The cutoff is this run's OWN worst case (one Google Places call timing
    out) plus a margin. Past that point the original attempt has either
    finished (and would have moved the status) or can no longer be alive, so
    reclaiming is safe rather than a race.
    """
    if discovery.status != "processing":
        return False
    started = discovery.started_at
    if started is None:
        # 'processing' with no start time is incoherent state; reclaim it.
        return True
    cutoff = settings.google_places_request_timeout_seconds + 120
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


def _find_by_external_id(db: Session, provider: str, external_place_id: str) -> Location | None:
    """An exact identity match: the strongest possible dedup signal. If this
    provider has already told us about this exact place, it's the same place,
    full stop -- no spatial or name check needed."""
    stmt = select(Location).where(
        Location.provider == provider, Location.external_place_id == external_place_id
    )
    return db.execute(stmt).scalars().first()


def find_similar_nearby_location(
    db: Session,
    latitude: float,
    longitude: float,
    name: str,
    *,
    radius_meters: float | None = None,
) -> Location | None:
    """An already-known place within the dedup radius whose NAME is also
    similar enough to be the same physical thing.

    Dedup used to be geography-only ("two places within a few tens of metres
    are treated as one"), which is right for the same feature appearing twice
    under slightly different spellings, but wrong for two genuinely different
    places that happen to be close together (a task's explicit example: "Tea
    Stall A" and "Tea Stall B" 40m apart must both survive). So this adds a
    name-similarity gate on top of the existing spatial gate -- close AND
    similarly named is a duplicate; close but differently named is not.

    Uses pg_trgm's indexable `%` operator (governed by the
    pg_trgm.similarity_threshold GUC, set for this query only) rather than a
    bare `similarity(...) >= x` function call, which the GIN trigram index on
    `locations.name` cannot use.

    Public (not `_`-prefixed) because this is the ONE dedup-by-name-and-
    proximity primitive in the codebase, and it is reused as-is by
    app/services/seed_import.py for curated data -- see that module's own
    docstring for why matching curated rows against existing Locations must
    use the identical rule discovery already uses, not a second
    implementation of "is this the same place?" `radius_meters` defaults to
    the standard discovery dedup radius but is overridable per-call, e.g. a
    curated row whose coordinate is only Low-confidence deliberately widens
    it (see seed_import.py) rather than risk missing a genuine match because
    the supplied pin might be a little off.
    """
    # SET LOCAL's value position is a GUC literal, not a bind parameter --
    # Postgres rejects `SET LOCAL x = $1` outright. Safe to inline directly:
    # this is a server-configured float from settings, never user input.
    threshold = float(settings.google_places_name_similarity_threshold)
    db.execute(text(f"SET LOCAL pg_trgm.similarity_threshold = {threshold}"))
    target = make_point(latitude, longitude)
    effective_radius = (
        radius_meters if radius_meters is not None else settings.poi_discovery_dedup_radius_meters
    )
    stmt = (
        select(Location)
        .where(
            func.ST_DWithin(Location.geog, target, effective_radius),
            Location.name.op("%")(name),
        )
        .order_by(func.ST_Distance(Location.geog, target))
        .limit(1)
    )
    return db.execute(stmt).scalars().first()


def _find_or_create_location(
    db: Session,
    *,
    name: str,
    latitude: float,
    longitude: float,
    provider: str,
    external_place_id: str | None,
    primary_type: str | None,
    types: list[str],
    formatted_address: str | None,
    source_url: str,
    discovery_cell_key: str | None,
) -> tuple[Location, bool]:
    """The one dedup-then-create code path, shared by the batch nearby-search
    persist loop and the single-place user-selected path.

    Returns `(location, created)` -- `created` is False whenever an existing
    Location already represents this place (exact id match or a close-enough
    name+spatial match) and True only for a genuinely new row, so callers can
    tell "resolved" from "discovered" without re-deriving it.
    """
    if external_place_id:
        existing = _find_by_external_id(db, provider, external_place_id)
        if existing is not None:
            return existing, False

    duplicate = find_similar_nearby_location(db, latitude, longitude, name)
    if duplicate is not None:
        logger.info("Skipped %r: already known as %r.", name, duplicate.name)
        return duplicate, False

    category, subcategory = categories.classify(primary_type, types, name)
    location = Location(
        name=name,
        description=f"A {primary_type.replace('_', ' ')} near here." if primary_type else None,
        latitude=latitude,
        longitude=longitude,
        geog=make_point(latitude, longitude),
        source="discovered",
        provider=provider,
        external_place_id=external_place_id,
        place_kind=primary_type,
        google_primary_type=primary_type,
        google_types=types or None,
        category=category,
        subcategory=subcategory,
        formatted_address=formatted_address,
        # A real, checkable citation: the place's own Google Maps link.
        source_urls=[source_url],
        discovery_cell_key=discovery_cell_key,
    )
    db.add(location)
    # Flushed immediately so a subsequent iteration/call in the same
    # transaction sees this row for its own dedup check.
    db.flush()
    return location, True


def ensure_discovered(
    db: Session,
    latitude: float,
    longitude: float,
    force: bool = False,
    *,
    timeout: float | None = None,
) -> PoiDiscovery:
    """Discovers real places around a coordinate if due (or if forced).

    Returns the discovery row in its resulting state. A 'failed' outcome is a
    legitimate, honest result -- callers should carry on with whatever places
    already exist rather than erroring.

    `timeout` overrides the Google request's default timeout -- used by
    extraction's inline call site, which needs a much tighter budget than
    the backgroundable /popular-questions trigger (see
    settings.google_places_inline_timeout_seconds).
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
        # duplicate the spend; the caller serves whatever exists meanwhile.
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
    locked.provider = PROVIDER_NAME
    # No model choice happens in this path anymore -- Google's typed results
    # are used directly, with no Claude judgement pass over them.
    locked.model = None
    # Releases the row lock BEFORE the external call.
    db.commit()

    try:
        candidates = get_place_provider().search_nearby_places(
            center_lat,
            center_lon,
            settings.poi_discovery_search_radius_meters,
            settings.poi_discovery_candidate_limit,
            timeout=timeout,
        )
    except PlaceProviderError as exc:
        failed = db.get(PoiDiscovery, discovery.id)
        failed.status = "failed"
        failed.error_message = str(getattr(exc, "message", exc))[:500]
        failed.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.warning("POI discovery failed for cell %s: %s", cell_key, type(exc).__name__)
        return failed

    kept = _persist_places(db, cell_key, center_lat, center_lon, candidates)

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


def _persist_places(
    db: Session,
    cell_key: str,
    center_lat: float,
    center_lon: float,
    candidates: list[DiscoveredPlace],
) -> int:
    """Creates Location rows for genuinely new places found by Nearby Search.

    Names and coordinates here came from Google Places, so there is no
    question of an invented landmark or an invented position. The distance
    check below is therefore a sanity check on OUR OWN query construction,
    not a hallucination guard: if a place comes back further from the cell
    centre than we asked for, the radius maths is wrong somewhere and the row
    is skipped rather than trusted.
    """
    kept = 0
    for place in candidates:
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

        _location, created = _find_or_create_location(
            db,
            name=place.name,
            latitude=place.latitude,
            longitude=place.longitude,
            provider=PROVIDER_NAME,
            external_place_id=place.external_place_id,
            primary_type=place.primary_type,
            types=place.types,
            formatted_address=place.formatted_address,
            source_url=place.source_url,
            discovery_cell_key=cell_key,
        )
        # Only count it toward this run's cap if it's genuinely new -- an
        # already-known place reused via dedup shouldn't crowd out a real new
        # discovery elsewhere in the same candidate list.
        if created:
            kept += 1
    return kept


def maybe_ensure_discovered(
    db: Session, latitude: float, longitude: float, *, timeout: float | None = None
) -> None:
    """Best-effort trigger. Never raises: a discovery failure must not break
    whatever the caller was actually doing. Mirrors
    place_questions.maybe_ensure_researched's swallow-everything contract.

    CHECKS TRAILMIND'S OWN LOCATIONS FIRST, via the exact same PostGIS lookup
    every other "is a known place nearby" decision in this system uses
    (geographic_context_radius_meters) -- if one already covers this exact
    coordinate, Google is never called at all, not even once the discovery
    cell itself goes stale. This is the cost-efficiency gate: Google Places
    is an enrichment layer for coordinates TrailMind doesn't already know
    about, never a database queried on every capture.
    """
    try:
        if location_service.find_nearest_location(
            db, latitude, longitude, settings.geographic_context_radius_meters
        ):
            return
        ensure_discovered(db, latitude, longitude, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 -- deliberate best-effort boundary
        logger.warning(
            "Best-effort POI discovery failed for %.5f,%.5f: %s",
            latitude,
            longitude,
            type(exc).__name__,
        )


def _find_containing_area_location(db: Session, latitude: float, longitude: float) -> Location | None:
    """An already-known AREA Location this coordinate can be considered inside.

    Matched on the category this system assigns areas, so it can never hand
    back a cafe as the answer to "which area is this", and tier by tier from
    most specific to least, so the tightest area containing the coordinate
    wins over the district that also contains it. See
    categories.AREA_REUSE_RADIUS_METERS for why the radius varies by tier.
    """
    target = make_point(latitude, longitude)
    distance = func.ST_Distance(Location.geog, target).label("distance_meters")
    widest = max(categories.AREA_REUSE_RADIUS_METERS.values())

    candidates = db.execute(
        select(Location, distance)
        .where(
            Location.category == categories.AREA_CATEGORY,
            func.ST_DWithin(Location.geog, target, widest),
        )
        .order_by(distance)
    ).all()

    for subcategory, radius in categories.AREA_REUSE_RADIUS_METERS.items():
        for location, distance_meters in candidates:
            if location.subcategory == subcategory and distance_meters <= radius:
                return location
    return None


def maybe_resolve_area_place(
    db: Session, latitude: float, longitude: float, *, timeout: float | None = None
) -> Location | None:
    """The named area a coordinate is actually INSIDE, as a Location.

    WHY THIS EXISTS, alongside nearby-POI discovery: those answer different
    questions, and only this one is answerable everywhere. Nearby search finds
    what is *around* a coordinate, and outside dense retail strips the closest
    listed POI is routinely several hundred metres away -- too far to honestly
    call it where someone is standing, which left a guide's position with no
    nameable place at all. A reverse geocode answers "where is here" directly,
    and returns a real, checkable, Google-sourced name ("Borabanda") for
    essentially any coordinate on land.

    The result is a Location like any other -- same table, same dedup, same
    provider/external_place_id provenance -- so everything downstream
    (research, question generation, observations) works on it unmodified.
    Areas are simply coarser places than POIs, not a parallel concept.

    Never raises, same best-effort convention as maybe_ensure_discovered.
    """
    try:
        # Cost gate. An area Location is stored at its CENTROID, which for
        # anything bigger than a small neighbourhood sits well outside the
        # tight context radius the caller already searched -- so without this,
        # every request from such a spot would re-pay for a geocode that can
        # only return the area we already have.
        existing = _find_containing_area_location(db, latitude, longitude)
        if existing is not None:
            return existing

        area = get_place_provider().reverse_geocode_area(latitude, longitude, timeout=timeout)
        if area is None:
            return None
        location, created = _find_or_create_location(
            db,
            name=area.name,
            latitude=area.latitude,
            longitude=area.longitude,
            provider=PROVIDER_NAME,
            external_place_id=area.external_place_id,
            primary_type=area.primary_type,
            types=area.types,
            formatted_address=area.formatted_address,
            source_url=area.source_url,
            discovery_cell_key=None,
        )
        db.commit()
        if created:
            logger.info("Resolved area %r for %.5f,%.5f.", area.name, latitude, longitude)
        return location
    except Exception as exc:  # noqa: BLE001 -- deliberate best-effort boundary
        db.rollback()
        logger.warning(
            "Best-effort area resolution failed for %.5f,%.5f: %s",
            latitude,
            longitude,
            type(exc).__name__,
        )
        return None


def maybe_resolve_user_selected_place(
    db: Session, external_place_id: str, latitude: float, longitude: float
) -> None:
    """Best-effort resolve/create a Location for a place the GUIDE THEMSELVES
    picked via search (location_source='user_selected'), keyed on its exact
    Google place id rather than a fresh Nearby Search.

    Called from extraction (see extractions.py) once per distinct place a
    guide ever selects -- an exact id match short-circuits everything for
    every later guide who selects (or lands near) the same place. Only calls
    Google's Place Details endpoint on a genuine miss, never speculatively.
    Never raises, same convention as maybe_ensure_discovered.
    """
    try:
        existing = _find_by_external_id(db, PROVIDER_NAME, external_place_id)
        if existing is not None:
            return
        details = get_place_provider().get_place_details(
            external_place_id, timeout=settings.google_places_inline_timeout_seconds
        )
        if details is None:
            return
        _location, _created = _find_or_create_location(
            db,
            name=details.name,
            latitude=details.latitude,
            longitude=details.longitude,
            provider=PROVIDER_NAME,
            external_place_id=details.external_place_id,
            primary_type=details.primary_type,
            types=details.types,
            formatted_address=details.formatted_address,
            source_url=details.source_url,
            discovery_cell_key=None,
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001 -- deliberate best-effort boundary
        db.rollback()
        logger.warning(
            "Best-effort user-selected place resolution failed for %s: %s",
            external_place_id,
            type(exc).__name__,
        )
