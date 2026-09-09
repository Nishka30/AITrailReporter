"""Provider-agnostic place-identification contract.

WHY THIS EXISTS: the application/service layer (poi_discovery.py,
place_questions.py, guides.py's place-search route) should call
`searchNearbyPlaces`-shaped methods, never a specific vendor's HTTP API
directly. Today the only implementation is Google (see google_provider.py),
but the contract itself names no vendor, so a second provider could be added
later without touching any caller.

This mirrors the existing `app/services/research/base.py` (ResearchProvider)
pattern already used for Perplexity -- same shape, same reasoning.
"""

from abc import ABC, abstractmethod


class PlaceProviderError(Exception):
    """Any failure that prevents a place-identification call from completing.
    `message` is always safe to persist and show -- no internals, no
    credentials."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class DiscoveredPlace:
    """One real, named place with real coordinates, from a place provider.

    Mirrors the old `osm_provider.OsmPlace` shape (name/latitude/longitude/
    place_kind/source_url) plus the provider-specific identity/typing fields
    a richer provider like Google supplies.
    """

    __slots__ = (
        "name",
        "latitude",
        "longitude",
        "external_place_id",
        "primary_type",
        "types",
        "formatted_address",
        "source_url",
    )

    def __init__(
        self,
        *,
        name: str,
        latitude: float,
        longitude: float,
        external_place_id: str | None,
        primary_type: str | None,
        types: list[str],
        formatted_address: str | None,
        source_url: str,
    ):
        self.name = name
        self.latitude = latitude
        self.longitude = longitude
        self.external_place_id = external_place_id
        self.primary_type = primary_type
        self.types = types
        self.formatted_address = formatted_address
        self.source_url = source_url


class PlaceCandidate:
    """One real, named place a guide could plausibly mean, for the
    place-search/autocomplete feature. Deliberately lighter than
    DiscoveredPlace -- a search suggestion the guide hasn't picked yet doesn't
    need full typing/address detail, only enough to render a label and, if
    picked, to resolve a Location later via `external_place_id`."""

    __slots__ = ("label", "latitude", "longitude", "external_place_id")

    def __init__(self, label: str, latitude: float, longitude: float, external_place_id: str | None):
        self.label = label
        self.latitude = latitude
        self.longitude = longitude
        self.external_place_id = external_place_id


class PlaceProvider(ABC):
    """What the application needs from a place-identification vendor.

    Every method is best-effort in spirit (callers wrap with their own
    swallow-all-exceptions boundary, same convention as today's
    `maybe_ensure_discovered`) but raises `PlaceProviderError` on failure
    rather than silently returning an empty result, so a caller that DOES
    need to distinguish "found nothing" from "the request failed" still can.
    """

    @abstractmethod
    def search_nearby_places(
        self,
        latitude: float,
        longitude: float,
        radius_meters: int,
        max_results: int,
        *,
        timeout: float | None = None,
    ) -> list[DiscoveredPlace]:
        """Real named places within radius of a coordinate. `timeout`
        overrides the provider's default when the caller has its own tighter
        budget (see extractions.py's inline discovery call)."""

    @abstractmethod
    def search_places(
        self,
        query: str,
        *,
        limit: int = 6,
        bias_latitude: float | None = None,
        bias_longitude: float | None = None,
        bias_radius_meters: float | None = None,
    ) -> list[PlaceCandidate]:
        """Real place candidates matching a free-text query, optionally
        biased (never restricted) toward an area."""

    @abstractmethod
    def reverse_geocode_locality(
        self, latitude: float, longitude: float, *, timeout: float | None = None
    ) -> str | None:
        """Human locality for a coordinate, e.g. "Koramangala, Bengaluru", or
        None if it can't be determined. Never raises."""

    @abstractmethod
    def reverse_geocode_area(
        self, latitude: float, longitude: float, *, timeout: float | None = None
    ) -> DiscoveredPlace | None:
        """The named AREA that actually contains this coordinate -- the
        neighbourhood/locality someone standing here would say they are in --
        or None if it can't be determined. Never raises.

        Distinct from search_nearby_places, which answers "what businesses and
        landmarks are around here". This answers "where is here", and unlike a
        nearby-POI lookup it has an answer essentially everywhere on land, so
        it is what keeps a guide's position nameable in the ordinary case of
        standing somewhere with no listed POI within range.
        """

    @abstractmethod
    def get_place_details(
        self, external_place_id: str, *, timeout: float | None = None
    ) -> DiscoveredPlace | None:
        """Full place metadata for a specific provider place id, or None if
        not found or the call failed (never raises). Used ONLY when a guide
        has already picked a place via search_places and its full metadata
        isn't otherwise available -- never called speculatively (see
        poi_discovery.py:maybe_resolve_user_selected_place)."""
