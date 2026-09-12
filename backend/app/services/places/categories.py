"""Maps Google's place taxonomy onto TrailMind's own categories.

WHY THIS IS A SEPARATE, SINGLE TABLE RATHER THAN SCATTERED IF/ELSE:
Google's `primaryType`/`types[]` are evidence, not TrailMind's vocabulary --
they change across Google API versions and are far more granular than what a
guide-facing question needs to distinguish. Keeping every Google-type ->
TrailMind-category mapping in one dict makes the taxonomy auditable and
extensible in one place, rather than re-derived ad hoc wherever a Location's
kind is used.

A type Google returns that isn't in this table is NOT a reason to discard the
place -- see classify()'s fallback. Google's raw `primary_type`/`types`/
`formatted_address` are preserved on the Location regardless of how (or
whether) they classify, specifically so classification can be improved later
without re-fetching anything.
"""

import re

# (TrailMind category, TrailMind subcategory), keyed by a Google Places (New)
# type string (https://developers.google.com/maps/documentation/places/web-service/place-types).
# Deliberately broad, not landmark-only -- see the module docstring in
# poi_discovery.py for why a rich, not just famous, geographic database is
# the goal.
GOOGLE_TYPE_MAP: dict[str, tuple[str, str]] = {
    # Trail
    "bridge": ("Trail", "Bridge"),
    "hiking_area": ("Trail", "Trailhead"),
    "campground": ("Trail", "Campsite"),
    "rv_park": ("Trail", "Campsite"),
    # Nature
    "mountain_peak": ("Nature", "Mountain Peak"),
    "lake": ("Nature", "Lake"),
    "river": ("Nature", "River"),
    "beach": ("Nature", "Beach"),
    "island": ("Nature", "Nature Reserve"),
    "woods": ("Nature", "Nature Reserve"),
    "nature_preserve": ("Nature", "Nature Reserve"),
    "national_park": ("Nature", "Nature Reserve"),
    "state_park": ("Nature", "Nature Reserve"),
    "park": ("Nature", "Nature Reserve"),
    "wildlife_park": ("Nature", "Nature Reserve"),
    "zoo": ("Nature", "Nature Reserve"),
    # Scenic Spot
    "scenic_spot": ("Scenic Spot", "Viewpoint"),
    "visitor_center": ("Scenic Spot", "Viewpoint"),
    "plaza": ("Scenic Spot", "Viewpoint"),
    # Culture & Heritage
    "church": ("Culture & Heritage", "Religious Site"),
    "mosque": ("Culture & Heritage", "Religious Site"),
    "synagogue": ("Culture & Heritage", "Religious Site"),
    "hindu_temple": ("Culture & Heritage", "Religious Site"),
    "buddhist_temple": ("Culture & Heritage", "Religious Site"),
    "shinto_shrine": ("Culture & Heritage", "Religious Site"),
    "museum": ("Culture & Heritage", "Museum"),
    "art_museum": ("Culture & Heritage", "Museum"),
    "history_museum": ("Culture & Heritage", "Museum"),
    "historical_place": ("Culture & Heritage", "Historical Site"),
    "historical_landmark": ("Culture & Heritage", "Historical Site"),
    "cultural_landmark": ("Culture & Heritage", "Historical Site"),
    "monument": ("Culture & Heritage", "Monument"),
    "tourist_attraction": ("Culture & Heritage", "Historical Site"),
    # Food & Drink
    "cafe": ("Food & Drink", "Cafe"),
    "restaurant": ("Food & Drink", "Restaurant"),
    "bakery": ("Food & Drink", "Bakery"),
    "market": ("Food & Drink", "Market"),
    "supermarket": ("Food & Drink", "Market"),
    "convenience_store": ("Food & Drink", "Market"),
    # Lodging
    "lodging": ("Lodging", "Guesthouse"),
}

# `includedTypes` sent to Nearby Search: every type this table knows how to
# classify. This IS the "don't import administrative/address noise" filter --
# Google's typed Places results never include raw addresses/boundaries the
# way a geocoder would, and restricting to this list keeps results to things
# a guide could plausibly stand at and report on.
NEARBY_SEARCH_INCLUDED_TYPES: list[str] = list(GOOGLE_TYPE_MAP)

# Reverse-geocoded AREAS (see google_provider.reverse_geocode_area) -- the
# neighbourhood/suburb/city a coordinate sits inside, rather than a POI a
# guide is standing at. Kept in a SEPARATE table from GOOGLE_TYPE_MAP on
# purpose: these are Geocoding API result types, not Places API types, and
# GOOGLE_TYPE_MAP is sent verbatim as Nearby Search's includedTypes, which
# would reject them.
AREA_CATEGORY = "Area"

# How far from a stored area's CENTROID a coordinate may sit and still be
# treated as "in that area", per tier, MOST SPECIFIC FIRST.
#
# An area Location stores a single centroid, not the region's outline, so
# containment has to be approximated by distance -- and the right distance
# depends entirely on how big the thing is. Measured against real Google data:
# a neighbourhood centroid lands ~100m from a coordinate inside it, while a
# village/mandal centroid can be ~8km from a coordinate inside THAT. One
# radius for both would either re-geocode constantly in the countryside or
# claim a whole district as someone's neighbourhood in a city.
#
# Order is what makes overlap safe: standing inside a neighbourhood that is
# also inside a district, the neighbourhood is the truthful answer, so it is
# checked first.
AREA_REUSE_RADIUS_METERS: dict[str, int] = {
    "Neighbourhood": 1_500,
    "Village or Ward": 10_000,
    "Town or City": 15_000,
    "District": 30_000,
}

GEOCODE_AREA_TYPE_MAP: dict[str, tuple[str, str]] = {
    "sublocality_level_2": (AREA_CATEGORY, "Neighbourhood"),
    "sublocality_level_1": (AREA_CATEGORY, "Neighbourhood"),
    "sublocality": (AREA_CATEGORY, "Neighbourhood"),
    "neighborhood": (AREA_CATEGORY, "Neighbourhood"),
    "administrative_area_level_4": (AREA_CATEGORY, "Village or Ward"),
    "locality": (AREA_CATEGORY, "Town or City"),
    "postal_town": (AREA_CATEGORY, "Town or City"),
    "administrative_area_level_3": (AREA_CATEGORY, "District"),
    "administrative_area_level_2": (AREA_CATEGORY, "District"),
}

# What classify() returns when nothing in the maps above matches. Public so a
# consumer can recognise "we could not say what this is" without re-deriving
# the literal -- see services/place_candidates.py, which ranks such places
# slightly lower rather than hiding them.
DEFAULT_CATEGORY: tuple[str, str] = ("Other", "Other")

_DEFAULT_CATEGORY = DEFAULT_CATEGORY

# A "cafe"-typed place whose name says "tea" is a tea stall, not a coffee
# shop -- a small, honest name-based refinement layered on top of the
# deterministic type mapping, not a replacement for it.
_TEA_NAME_RE = re.compile(r"\btea\b", re.IGNORECASE)


def classify(
    primary_type: str | None, types: list[str] | None, name: str | None
) -> tuple[str, str]:
    """TrailMind (category, subcategory) for a Google-typed place.

    Never fails to return a value -- an unrecognised type maps to
    ("Other", "Other") rather than causing the place to be discarded. See the
    module docstring: Google's raw type data survives on the Location either
    way, so classification can improve later without new data collection.
    """
    if primary_type and primary_type in GOOGLE_TYPE_MAP:
        category, subcategory = GOOGLE_TYPE_MAP[primary_type]
    elif primary_type and primary_type in GEOCODE_AREA_TYPE_MAP:
        category, subcategory = GEOCODE_AREA_TYPE_MAP[primary_type]
    else:
        category, subcategory = _DEFAULT_CATEGORY
        for candidate_type in types or []:
            if candidate_type in GOOGLE_TYPE_MAP:
                category, subcategory = GOOGLE_TYPE_MAP[candidate_type]
                break
            if candidate_type in GEOCODE_AREA_TYPE_MAP:
                category, subcategory = GEOCODE_AREA_TYPE_MAP[candidate_type]
                break

    is_cafe_like = primary_type == "cafe" or "cafe" in (types or [])
    if is_cafe_like and name and _TEA_NAME_RE.search(name):
        return ("Food & Drink", "Tea Stall")

    return category, subcategory
