"""Forward geocoding ("Kedarnath" -> real coordinates) for place autocomplete.

WHY NOMINATIM AGAIN: this project already depends on OpenStreetMap's Nominatim
for reverse geocoding (app/services/poi_discovery_research/osm_provider.py's
reverse_geocode_locality). Forward geocoding is the same service, the same
free/keyless usage model, and the same usage-policy obligations (descriptive
User-Agent, roughly one request per second) -- reusing it here means a guide
selecting "Kedarnath Temple" from a search box costs no new provider,
dependency, or API key.

WHAT THIS IS FOR: a guide describing an old memory or photo who does not know
(or is not near) exact coordinates. They type a place name; this returns real,
named candidates with real coordinates; the guide confirms one; the result is
stored with location_source='user_selected' -- a human judgement, not a
sensor reading, but a REAL place either way (see
app/db/models/submission.py:SUBMISSION_LOCATION_SOURCES).

NOT for resolving "what is near this guide right now" -- that is discovery
(poi_discovery.py), a different problem this module has no part in.
"""

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Same identification obligation as osm_provider.py's Overpass client --
# Nominatim's usage policy requires a descriptive User-Agent identifying the
# application, not a generic HTTP client string.
_USER_AGENT = "TrailMind/1.0 (trail knowledge app; contact via app operator)"


class GeocodingProviderError(Exception):
    """Any failure that prevents a search. `message` is always safe to persist
    and show -- no internals, no credentials (there are none)."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class PlaceCandidate:
    """One real, named place a guide could plausibly mean."""

    __slots__ = ("label", "latitude", "longitude")

    def __init__(self, label: str, latitude: float, longitude: float):
        self.label = label
        self.latitude = latitude
        self.longitude = longitude


def search_places(
    query: str,
    limit: int = 6,
    bounding_box: tuple[float, float, float, float] | None = None,
) -> list[PlaceCandidate]:
    """Real place candidates matching `query`, from OpenStreetMap.

    `bounding_box` (min_lat, min_lon, max_lat, max_lon), when supplied, is a
    SOFT bias toward that area (Nominatim's `bounded=0` -- results outside it
    can still appear, just ranked lower). This is deliberately not a hard
    restriction: a guide is always allowed to describe a memory from
    somewhere they've never recorded a GPS ping, and a search that could only
    ever return "nearby" results would silently fail every guide describing
    their very first trip somewhere new.

    Raises GeocodingProviderError on any failure; never fabricates a result.
    """
    query = query.strip()
    if not query:
        return []

    params: dict = {
        "q": query,
        "format": "jsonv2",
        "limit": limit,
        "addressdetails": 0,
        "accept-language": "en",
    }
    if bounding_box is not None:
        min_lat, min_lon, max_lat, max_lon = bounding_box
        # Nominatim's viewbox is (left, top, right, bottom) = (min_lon,
        # max_lat, max_lon, min_lat) -- easy to transpose, so ordered
        # explicitly here rather than passed through positionally.
        params["viewbox"] = f"{min_lon},{max_lat},{max_lon},{min_lat}"
        params["bounded"] = 0

    try:
        response = httpx.get(
            settings.osm_nominatim_search_url,
            params=params,
            headers={"User-Agent": _USER_AGENT},
            timeout=settings.osm_request_timeout_seconds,
        )
        response.raise_for_status()
        results = response.json()
    except httpx.HTTPStatusError as exc:
        logger.warning("Nominatim search returned status %s", exc.response.status_code)
        raise GeocodingProviderError(f"Place search failed (status {exc.response.status_code}).") from exc
    except Exception as exc:
        logger.warning("Nominatim search request failed: %s", type(exc).__name__)
        raise GeocodingProviderError("Could not reach the place search service.") from exc

    candidates: list[PlaceCandidate] = []
    for item in results if isinstance(results, list) else []:
        name = item.get("display_name")
        lat = item.get("lat")
        lon = item.get("lon")
        if not name or lat is None or lon is None:
            continue
        try:
            candidates.append(PlaceCandidate(label=str(name)[:255], latitude=float(lat), longitude=float(lon)))
        except (TypeError, ValueError):
            continue

    return candidates
