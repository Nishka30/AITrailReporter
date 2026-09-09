"""The ONLY file in this codebase that talks to Google Maps Platform.

Same isolation rule as every other provider here (Sarvam, Anthropic,
Perplexity, and the OpenStreetMap module this replaces): the SDK/wire format
lives in exactly one module, and the rest of the system depends on the
neutral `PlaceProvider` contract in base.py.

APIs used (verified against current docs, not assumed from an older syntax):
  - Places API (New) Nearby Search  -- POST .../v1/places:searchNearby
  - Places API (New) Text Search    -- POST .../v1/places:searchText
  - Places API (New) Place Details  -- GET  .../v1/places/{id}
  - Geocoding API (reverse)         -- GET  maps.googleapis.com/maps/api/geocode/json
    (Places API New has no reverse-geocode method; the classic Geocoding API
    is the current, non-deprecated service for lat/lng -> address.)

Field masks are used throughout so only the fields actually needed are
requested, per Google's cost-efficiency guidance -- see the `X-Goog-FieldMask`
header on every Places (New) call below.
"""

import logging
import re
import time

import httpx

from app.core.config import settings
from app.services.places.base import (
    DiscoveredPlace,
    PlaceCandidate,
    PlaceProvider,
    PlaceProviderError,
)

logger = logging.getLogger(__name__)

PROVIDER_NAME = "google"

_PLACES_BASE_URL = "https://places.googleapis.com/v1/places"
_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

_NEARBY_FIELD_MASK = "places.id,places.displayName,places.types,places.primaryType,places.location,places.formattedAddress"
_TEXT_SEARCH_FIELD_MASK = "places.id,places.displayName,places.location"
_DETAILS_FIELD_MASK = "id,displayName,types,primaryType,location,formattedAddress"

# Google's own hard cap on Nearby Search's maxResultCount -- a configured
# poi_discovery_candidate_limit above this is silently clamped, never sent
# as-is (the API would reject it).
_MAX_NEARBY_RESULTS = 20

# Same two-tier "<neighbourhood>, <city>" composition as the OSM module this
# replaces, just over Google's address_component `types` vocabulary instead
# of Nominatim's flat `address` dict.
_LOCAL_COMPONENT_TYPES = ("sublocality_level_1", "sublocality", "neighborhood")
_REGION_COMPONENT_TYPES = ("locality", "administrative_area_level_2", "administrative_area_level_1")

# Same defensive filter as the OSM module's _ADMINISTRATIVE_RE -- Google's
# locality/sublocality names are curated far better than raw OSM tags, but
# costs nothing to guard against the rare bureaucratic-sounding component.
_ADMINISTRATIVE_RE = re.compile(r"(?i)\b(ward|corporation|municipal(ity)?|panchayat|taluk|tehsil|subdistrict|sub-district|zone|constituency|division)\b")

# Area-level reverse-geocode results, TIGHTEST FIRST. A reverse geocode returns
# the whole containing hierarchy at once -- street address, neighbourhood,
# suburb, city, state, country -- and this picks which rung to call "where you
# are". Street-level rungs are deliberately excluded: a guide's exact postal
# address is both more precision than the app ever needs and the guide's own
# home in the commonest case. Country/state rungs are excluded at the other
# end as too coarse to be worth naming.
# The administrative rungs matter as much as the sublocality ones: outside
# cities there is frequently no sublocality/locality at all, and the village
# name lives in administrative_area_level_4. Ordered tightest-first, with
# level_4 ahead of `locality` on purpose -- a village or ward is a better
# answer to "where am I" than the whole city it belongs to.
_AREA_RESULT_TYPES = (
    "sublocality_level_2",
    "sublocality_level_1",
    "sublocality",
    "neighborhood",
    "administrative_area_level_4",
    "locality",
    "postal_town",
    "administrative_area_level_3",
    "administrative_area_level_2",
)

# How long a place-search result is reused for the same (normalized query,
# coarse bias bucket) pair. Text Search is billed per request, unlike the
# free Nominatim it replaces, and the mobile debounce (350ms) alone gives no
# request ceiling -- this catches repeat/near-duplicate queries across guides
# without needing new infrastructure.
_SEARCH_CACHE_TTL_SECONDS = 600.0
_search_cache: dict[tuple[str, int, int], tuple[float, list[PlaceCandidate]]] = {}


def _require_api_key() -> str:
    if not settings.google_maps_api_key:
        raise PlaceProviderError("Place discovery is not configured on the server.")
    return settings.google_maps_api_key


def _display_name(place: dict) -> str:
    name = place.get("displayName")
    if isinstance(name, dict):
        return str(name.get("text") or "").strip()
    return str(name or "").strip()


class GooglePlaceProvider(PlaceProvider):
    def search_nearby_places(
        self,
        latitude: float,
        longitude: float,
        radius_meters: int,
        max_results: int,
        *,
        timeout: float | None = None,
    ) -> list[DiscoveredPlace]:
        # Deferred import: categories.py has no reason to depend on this
        # module, but this module needs its allowlist -- avoids a cycle.
        from app.services.places.categories import NEARBY_SEARCH_INCLUDED_TYPES

        api_key = _require_api_key()
        body = {
            "includedTypes": NEARBY_SEARCH_INCLUDED_TYPES,
            "maxResultCount": min(max(max_results, 1), _MAX_NEARBY_RESULTS),
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": latitude, "longitude": longitude},
                    "radius": radius_meters,
                }
            },
        }
        try:
            response = httpx.post(
                f"{_PLACES_BASE_URL}:searchNearby",
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": api_key,
                    "X-Goog-FieldMask": _NEARBY_FIELD_MASK,
                },
                timeout=timeout if timeout is not None else settings.google_places_request_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            logger.warning("Google Nearby Search returned status %s", exc.response.status_code)
            raise PlaceProviderError(f"Place discovery request failed (status {exc.response.status_code}).") from exc
        except Exception as exc:
            logger.warning("Google Nearby Search request failed: %s", type(exc).__name__)
            raise PlaceProviderError("Could not reach the place discovery service.") from exc

        places: list[DiscoveredPlace] = []
        for item in payload.get("places") or []:
            name = _display_name(item)
            location = item.get("location") or {}
            lat, lon = location.get("latitude"), location.get("longitude")
            place_id = item.get("id")
            if not name or lat is None or lon is None or not place_id:
                continue
            places.append(
                DiscoveredPlace(
                    name=name[:255],
                    latitude=float(lat),
                    longitude=float(lon),
                    external_place_id=str(place_id),
                    primary_type=item.get("primaryType"),
                    types=[t for t in (item.get("types") or []) if isinstance(t, str)],
                    formatted_address=item.get("formattedAddress"),
                    source_url=f"https://www.google.com/maps/place/?q=place_id:{place_id}",
                )
            )
        logger.info("Google Nearby Search returned %d place(s).", len(places))
        return places

    def search_places(
        self,
        query: str,
        *,
        limit: int = 6,
        bias_latitude: float | None = None,
        bias_longitude: float | None = None,
        bias_radius_meters: float | None = None,
    ) -> list[PlaceCandidate]:
        query = query.strip()
        if not query:
            return []

        bucket_lat = round(bias_latitude, 2) if bias_latitude is not None else 0
        bucket_lon = round(bias_longitude, 2) if bias_longitude is not None else 0
        cache_key = (query.casefold(), bucket_lat, bucket_lon)
        cached = _search_cache.get(cache_key)
        if cached is not None and time.monotonic() - cached[0] < _SEARCH_CACHE_TTL_SECONDS:
            return cached[1]

        api_key = _require_api_key()
        body: dict = {"textQuery": query, "pageSize": max(1, min(limit, 20))}
        if bias_latitude is not None and bias_longitude is not None and bias_radius_meters:
            body["locationBias"] = {
                "circle": {
                    "center": {"latitude": bias_latitude, "longitude": bias_longitude},
                    "radius": min(bias_radius_meters, 50_000),
                }
            }

        try:
            response = httpx.post(
                f"{_PLACES_BASE_URL}:searchText",
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": api_key,
                    "X-Goog-FieldMask": _TEXT_SEARCH_FIELD_MASK,
                },
                timeout=settings.google_places_request_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            logger.warning("Google Text Search returned status %s", exc.response.status_code)
            raise PlaceProviderError(f"Place search failed (status {exc.response.status_code}).") from exc
        except Exception as exc:
            logger.warning("Google Text Search request failed: %s", type(exc).__name__)
            raise PlaceProviderError("Could not reach the place search service.") from exc

        candidates: list[PlaceCandidate] = []
        for item in payload.get("places") or []:
            name = _display_name(item)
            location = item.get("location") or {}
            lat, lon = location.get("latitude"), location.get("longitude")
            place_id = item.get("id")
            if not name or lat is None or lon is None:
                continue
            candidates.append(
                PlaceCandidate(
                    label=name[:255],
                    latitude=float(lat),
                    longitude=float(lon),
                    external_place_id=str(place_id) if place_id else None,
                )
            )

        _search_cache[cache_key] = (time.monotonic(), candidates)
        return candidates

    def reverse_geocode_locality(
        self, latitude: float, longitude: float, *, timeout: float | None = None
    ) -> str | None:
        try:
            response = httpx.get(
                _GEOCODE_URL,
                params={
                    "latlng": f"{latitude},{longitude}",
                    "language": "en",
                    "key": _require_api_key(),
                },
                timeout=timeout if timeout is not None else settings.google_places_request_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001 -- deliberate best-effort boundary
            logger.warning("Reverse geocode failed: %s", type(exc).__name__)
            return None

        results = payload.get("results") or []
        if not results:
            return None
        components = results[0].get("address_components") or []

        def _first_useful(target_types: tuple[str, ...]) -> str | None:
            for target_type in target_types:
                for component in components:
                    if target_type in (component.get("types") or []):
                        value = str(component.get("long_name") or "").strip()
                        if value and not _ADMINISTRATIVE_RE.search(value):
                            return value
            return None

        parts: list[str] = []
        for value in (_first_useful(_LOCAL_COMPONENT_TYPES), _first_useful(_REGION_COMPONENT_TYPES)):
            if value is None:
                continue
            if any(value in part or part in value for part in parts):
                continue
            parts.append(value)
        if not parts:
            return None
        return ", ".join(parts)[:255]

    def reverse_geocode_area(
        self, latitude: float, longitude: float, *, timeout: float | None = None
    ) -> DiscoveredPlace | None:
        try:
            response = httpx.get(
                _GEOCODE_URL,
                params={
                    "latlng": f"{latitude},{longitude}",
                    "language": "en",
                    "key": _require_api_key(),
                },
                timeout=timeout if timeout is not None else settings.google_places_request_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001 -- deliberate best-effort boundary
            logger.warning("Reverse geocode (area) failed: %s", type(exc).__name__)
            return None

        results = payload.get("results") or []
        if not results:
            return None

        # One pass per rung rather than per result, so the TIGHTEST available
        # area always wins regardless of the order Google returned them in.
        by_type: dict[str, dict] = {}
        for result in results:
            for result_type in result.get("types") or []:
                by_type.setdefault(result_type, result)

        chosen = next((by_type[t] for t in _AREA_RESULT_TYPES if t in by_type), None)
        if chosen is None:
            return None

        # The name is the matching component's own short label ("Borabanda"),
        # not the full comma-separated address -- formatted_address keeps that.
        types = list(chosen.get("types") or [])
        primary_type = next((t for t in _AREA_RESULT_TYPES if t in types), None)
        name: str | None = None
        for component in chosen.get("address_components") or []:
            if primary_type in (component.get("types") or []):
                candidate = str(component.get("long_name") or "").strip()
                if candidate and not _ADMINISTRATIVE_RE.search(candidate):
                    name = candidate
                break
        if not name:
            return None

        location = chosen.get("geometry", {}).get("location") or {}
        area_lat, area_lon = location.get("lat"), location.get("lng")
        if area_lat is None or area_lon is None:
            return None

        place_id = chosen.get("place_id")
        return DiscoveredPlace(
            name=name,
            latitude=float(area_lat),
            longitude=float(area_lon),
            external_place_id=place_id,
            primary_type=primary_type,
            types=types,
            formatted_address=chosen.get("formatted_address"),
            source_url=(
                f"https://www.google.com/maps/place/?q=place_id:{place_id}"
                if place_id
                else f"https://www.google.com/maps/search/?api=1&query={area_lat},{area_lon}"
            ),
        )

    def get_place_details(
        self, external_place_id: str, *, timeout: float | None = None
    ) -> DiscoveredPlace | None:
        try:
            response = httpx.get(
                f"{_PLACES_BASE_URL}/{external_place_id}",
                headers={
                    "X-Goog-Api-Key": _require_api_key(),
                    "X-Goog-FieldMask": _DETAILS_FIELD_MASK,
                },
                timeout=timeout if timeout is not None else settings.google_places_request_timeout_seconds,
            )
            response.raise_for_status()
            item = response.json()
        except Exception as exc:  # noqa: BLE001 -- deliberate best-effort boundary
            logger.warning("Google Place Details failed for %s: %s", external_place_id, type(exc).__name__)
            return None

        name = _display_name(item)
        location = item.get("location") or {}
        lat, lon = location.get("latitude"), location.get("longitude")
        if not name or lat is None or lon is None:
            return None
        return DiscoveredPlace(
            name=name[:255],
            latitude=float(lat),
            longitude=float(lon),
            external_place_id=external_place_id,
            primary_type=item.get("primaryType"),
            types=[t for t in (item.get("types") or []) if isinstance(t, str)],
            formatted_address=item.get("formattedAddress"),
            source_url=f"https://www.google.com/maps/place/?q=place_id:{external_place_id}",
        )


def get_place_provider() -> GooglePlaceProvider:
    """The configured place provider. A single call site to change when a
    second provider is added -- mirrors research/perplexity_provider.get_provider()."""
    return GooglePlaceProvider()
