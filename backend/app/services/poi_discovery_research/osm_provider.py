"""Real named places and their coordinates, from OpenStreetMap.

WHY THIS EXISTS INSTEAD OF ASKING THE MODEL FOR COORDINATES

The first version of discovery asked Claude (with web search) to return places
AND their latitude/longitude, with a rule that a place whose position could not
be sourced must be dropped. It behaved exactly as instructed and returned
nothing at all: five searches came back with 46 results, and every candidate was
discarded, because web pages publish names and descriptions but essentially
never publish coordinates. The anti-hallucination guard was strict enough to
make the feature impossible.

The fix is structural rather than a loosened rule. Coordinates now come from a
geographic database, so a language model is never in a position to invent one:

    OpenStreetMap  ->  what exists here, and exactly where          (facts)
    Claude         ->  which of these are worth asking about        (judgement)

That division is also just the right tool for each job. OSM is authoritative
about geography and says nothing about significance; the model is the opposite.

OSM is already part of this project's stack -- the traveller website renders
OpenStreetMap tiles through Leaflet -- so this introduces a data source the
project already depends on rather than a new one.

USAGE POLICY: Overpass is a free, donated service. This module sends ONE
request per discovery grid cell, and results are cached for
`poi_discovery_refresh_days`, so a neighbourhood costs one query rather than one
per guide or one per GPS reading. A descriptive User-Agent is sent as the
service's usage policy requires.
"""

import logging
import re

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Identifies this application to Overpass, as its usage policy requires.
_USER_AGENT = "TrailMind/1.0 (trail knowledge app; contact via app operator)"

# Which OSM tags count as "a place a guide could stand at and report on".
#
# Deliberately curated rather than "anything with a name": OSM names a great
# deal that is useless here -- roads, bus stops, ATMs, individual shops in a
# mall, administrative boundaries. Each entry is (tag_key, regex_of_values);
# an empty regex means "any value for this key".
_PLACE_FILTERS: list[tuple[str, str]] = [
    # Things people travel to see.
    ("tourism", "attraction|viewpoint|museum|artwork|gallery|picnic_site|information"),
    ("historic", ""),
    ("natural", "peak|spring|waterfall|cave_entrance|beach|water"),
    # Places people stop at, which is what makes a trail report useful.
    ("amenity", "cafe|restaurant|marketplace|place_of_worship|library|theatre|fountain|shelter|drinking_water"),
    ("leisure", "park|garden|nature_reserve|sports_centre|stadium"),
    # Trail and crossing features -- the Hillary-Bridge shape of place.
    ("man_made", "bridge|pier|lighthouse|water_well|watermill"),
    ("bridge", ""),
    ("mountain_pass", ""),
    ("shop", "bakery|tea|coffee|greengrocer|convenience"),
]

# Overpass truncates by internal element id, NOT by relevance or distance, so a
# plain limit is biased by whatever is densest locally. A first run in central
# Bangalore came back as 38 restaurants and 2 temples -- the parks, viewpoints
# and historic sites within the same radius were simply cut off before they
# were ever seen. So more is fetched than is returned, and the trimming to the
# caller's limit is done by _interleave_by_kind below, which is diversity-aware.
_WIRE_LIMIT_MULTIPLIER = 5
_MAX_WIRE_LIMIT = 250


class OsmProviderError(Exception):
    """Any failure that prevents retrieving places. `message` is safe to
    persist and show -- no internals, no credentials (there are none)."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class OsmPlace:
    """One real, named place with real coordinates, straight from OSM."""

    __slots__ = ("name", "latitude", "longitude", "place_kind", "osm_id")

    def __init__(self, name: str, latitude: float, longitude: float, place_kind: str, osm_id: str):
        self.name = name
        self.latitude = latitude
        self.longitude = longitude
        self.place_kind = place_kind
        self.osm_id = osm_id

    @property
    def source_url(self) -> str:
        """A real, checkable citation for this place's existence and position.
        Every discovered Location carries one, so provenance is never taken on
        trust."""
        return f"https://www.openstreetmap.org/{self.osm_id}"


# A locality is built from TWO tiers, not from "the two most specific fields
# available". Taking the top two of one ordered list produced "Kormangala East,
# ST Bed Layout" -- two names for the same few streets and no city at all,
# which is barely more searchable than the bare place name.
#
# One name from each tier gives the shape people actually write:
# "<neighbourhood>, <city>".
#
# `suburb` leads the local tier deliberately: at one coordinate Nominatim
# returns suburb="Koramangala" and neighbourhood="Koramangala 6th Block", and
# the former is what anyone writing about the area calls it.
_LOCAL_FIELDS = ("suburb", "neighbourhood", "quarter", "village", "hamlet", "town")
# Falls through to county/state for rural areas, which frequently have no city
# and no suburb -- around Everest only "Solukhumbu" resolves, and that is
# genuinely the right name for it.
_REGION_FIELDS = ("city", "town", "municipality", "county", "state")

# Administrative names that identify a place to a government but to nobody
# else. This is not a cosmetic filter -- it decides whether web research
# succeeds. The first run of this code searched for a temple in "Sri Lakshmi
# Devi Ward, Bengaluru South City Corporation" and found nothing whatsoever,
# because no page about that temple has ever used those words. The same temple
# in "Koramangala, Bengaluru" is documented in detail.
_ADMINISTRATIVE_RE = re.compile(
    r"(?i)\b(ward|corporation|municipal(ity)?|panchayat|taluk|tehsil|"
    r"subdistrict|sub-district|zone|constituency|division)\b"
    # Also numbered administrative units like "Khumbupasanglahmu-04", which are
    # census identifiers rather than names anyone uses.
    r"|-\d+$"
)


def _is_useful_locality(value: str) -> bool:
    return bool(value) and not _ADMINISTRATIVE_RE.search(value)


def reverse_geocode_locality(latitude: float, longitude: float) -> str | None:
    """Human locality for a coordinate, e.g. "Koramangala, Bengaluru".

    WHY THIS MATTERS MORE THAN IT LOOKS: it is what makes web research about a
    place possible at all. Searching for "Ganesh Temple" returns noise from
    every city on earth; searching for "Ganesh Temple in Koramangala,
    Bengaluru" returns the right building. One call per place, then stored.

    Best-effort by contract: returns None rather than raising, because a place
    with no resolved locality is still researchable by name, just less well.
    """
    try:
        response = httpx.get(
            settings.osm_nominatim_url,
            params={
                "lat": latitude,
                "lon": longitude,
                "format": "jsonv2",
                # 16 = building/street level detail in the ADDRESS breakdown,
                # which is what carries the colloquial suburb name. Measured,
                # not guessed: at zoom 14 the same coordinate resolved only to
                # an administrative ward, while 16 returned "Koramangala".
                "zoom": 16,
                "addressdetails": 1,
                # Without this, localities come back in the local script
                # (Devanagari around Everest), which searches far worse.
                "accept-language": "en",
            },
            headers={"User-Agent": _USER_AGENT},
            timeout=settings.osm_request_timeout_seconds,
        )
        response.raise_for_status()
        address = response.json().get("address") or {}
    except Exception as exc:  # noqa: BLE001 -- deliberate best-effort boundary
        logger.warning("Reverse geocode failed: %s", type(exc).__name__)
        return None

    def _first_useful(fields: tuple[str, ...]) -> str | None:
        for field in fields:
            value = address.get(field)
            if isinstance(value, str) and _is_useful_locality(value.strip()):
                return value.strip()
        return None

    parts: list[str] = []
    for value in (_first_useful(_LOCAL_FIELDS), _first_useful(_REGION_FIELDS)):
        if value is None:
            continue
        # Skip anything that restates what we already have: "Koramangala" then
        # "Koramangala 6th Block" is one place named twice, and the extra
        # precision narrows a web search for no benefit.
        if any(value in part or part in value for part in parts):
            continue
        parts.append(value)
    if not parts:
        return None

    country = address.get("country")
    if isinstance(country, str) and country.strip() and country not in parts:
        parts.append(country.strip())
    return ", ".join(parts)[:255]


def _build_query(latitude: float, longitude: float, radius_meters: int, limit: int) -> str:
    """Overpass QL for named places of interest within a radius.

    Queries nodes AND ways: a cafe is usually a node, but a park, a bridge or a
    temple compound is normally a way. `out center` gives ways a single
    representative coordinate, so both kinds come back in one shape.
    """
    clauses = []
    for key, values in _PLACE_FILTERS:
        selector = f'["{key}"~"{values}"]' if values else f'["{key}"]'
        for element in ("node", "way"):
            clauses.append(f'{element}(around:{radius_meters},{latitude},{longitude})["name"]{selector};')
    body = "".join(clauses)
    return f"[out:json][timeout:{settings.osm_request_timeout_seconds:.0f}];({body});out center {limit};"


def _element_kind(tags: dict) -> str:
    """The most specific descriptive kind available for this element."""
    for key in ("tourism", "historic", "natural", "amenity", "leisure", "man_made", "shop"):
        value = tags.get(key)
        if value:
            return str(value).replace("_", " ")[:50]
    if tags.get("bridge"):
        return "bridge"
    if tags.get("mountain_pass"):
        return "mountain pass"
    return "place"


def _interleave_by_kind(places: list[OsmPlace], limit: int) -> list[OsmPlace]:
    """Trims to `limit` while preserving the VARIETY of what is actually here.

    Straight truncation lets one dense category bury everything else: a busy
    restaurant strip returns forty restaurants and hides the temple, the park
    and the viewpoint on the same street. Taking one place per kind in rotation
    means every category present in the area survives into the candidate list,
    and the abundant ones give up their surplus first.

    Order within a kind is left exactly as OSM returned it -- no re-ranking is
    invented here, because nothing in this module knows which restaurant is the
    better one. That judgement belongs to selection.py.
    """
    by_kind: dict[str, list[OsmPlace]] = {}
    for place in places:
        by_kind.setdefault(place.place_kind, []).append(place)

    trimmed: list[OsmPlace] = []
    while len(trimmed) < limit:
        added = False
        for bucket in by_kind.values():
            if not bucket:
                continue
            trimmed.append(bucket.pop(0))
            added = True
            if len(trimmed) >= limit:
                break
        if not added:
            break  # every bucket drained; the area simply has fewer places
    return trimmed


def fetch_places(latitude: float, longitude: float, radius_meters: int, limit: int) -> list[OsmPlace]:
    """Up to `limit` named places within radius, from OpenStreetMap.

    Raises OsmProviderError on any failure; never fabricates a result and never
    returns a place without a real name and real coordinates.
    """
    wire_limit = min(max(limit * _WIRE_LIMIT_MULTIPLIER, limit), _MAX_WIRE_LIMIT)
    query = _build_query(latitude, longitude, radius_meters, wire_limit)
    try:
        response = httpx.post(
            settings.osm_overpass_url,
            data={"data": query},
            headers={"User-Agent": _USER_AGENT},
            timeout=settings.osm_request_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as exc:
        logger.warning("Overpass returned status %s", exc.response.status_code)
        raise OsmProviderError(f"Map data request failed (status {exc.response.status_code}).") from exc
    except Exception as exc:
        logger.warning("Overpass request failed: %s", type(exc).__name__)
        raise OsmProviderError("Could not reach the map data service.") from exc

    places: list[OsmPlace] = []
    seen_names: set[str] = set()
    for element in payload.get("elements", []):
        tags = element.get("tags") or {}
        name = (tags.get("name") or "").strip()
        if not name:
            continue
        # A way reports its representative point under `center`; a node carries
        # lat/lon directly.
        lat = element.get("lat")
        lon = element.get("lon")
        if lat is None or lon is None:
            center = element.get("center") or {}
            lat, lon = center.get("lat"), center.get("lon")
        if lat is None or lon is None:
            continue
        # OSM frequently holds the same feature as both a node and an enclosing
        # way. Name-level dedup here is cheap; poi_discovery.py still applies
        # the authoritative geographic dedup before anything is stored.
        key = name.casefold()
        if key in seen_names:
            continue
        seen_names.add(key)
        places.append(
            OsmPlace(
                name=name[:255],
                latitude=float(lat),
                longitude=float(lon),
                place_kind=_element_kind(tags),
                osm_id=f"{element.get('type', 'node')}/{element.get('id')}",
            )
        )

    trimmed = _interleave_by_kind(places, limit)
    logger.info(
        "OSM returned %d named place(s) across %d kind(s); kept %d.",
        len(places),
        len({p.place_kind for p in places}),
        len(trimmed),
    )
    return trimmed
