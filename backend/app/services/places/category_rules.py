"""Deterministic Location -> categories classification.

THE CONTRACT: given what is already known about an ALREADY-IDENTIFIED place
(Google's types, the curated spreadsheet's type column, the place's name),
produce the set of categories that genuinely describe it -- with a relevance
and a confidence for each.

This never identifies a place and never touches coordinates. Identification
is the existing Google/GPS pipeline's job (poi_discovery.py); by the time
anything here runs, we already know WHICH place we are talking about. The
same boundary applies to the AI fallback in category_ai.py: it classifies a
known place, it never decides what place a coordinate is.

WHY DETERMINISTIC FIRST, AI ONLY AS FALLBACK:
Most places classify perfectly from data we already paid for. Google says
`hindu_temple`; that is not a judgement call. Running a model over it would
add cost, latency and variance for no gain -- and would make the SAME place
classify differently on two runs. So rules run first, always, and the model
is asked only about places the rules genuinely could not describe (see
`is_weak`). That is also what keeps assignments sparse: rules only ever emit
what a place_type actually implies, so nothing accumulates a long tail of
vaguely-related categories.

HOW MULTI-CATEGORY IS PRODUCED WITHOUT GUESSWORK:
One place_type is resolved (`hindu_temple` -> `temple`), and the catalog
already declares what that type implies (`temple` -> religious 95,
culture_heritage 90, historical 70). So a single Google type yields a whole
honest category set, identically every time. See category_catalog.py.
"""

import re
from dataclasses import dataclass

from app.services.places import category_catalog as catalog

# Where an assignment came from. Ordered loosely most-to-least authoritative;
# nothing depends on the order, but it is the right mental ranking.
#   'seed_type'    -- a curator's own type column (a human said so)
#   'google_type'  -- Google's primaryType / types[]
#   'name_rule'    -- a pattern in the place's own name refined the type
#   'rule_implied' -- a theme the resolved place_type implies, per the catalog
#   'ai'           -- the constrained model fallback (category_ai.py)
#   'manual'       -- a human edited this assignment directly. NEVER
#                     overwritten by reclassification; see category_assignment.
ASSIGNMENT_SOURCES = (
    "seed_type",
    "google_type",
    "name_rule",
    "rule_implied",
    "ai",
    "manual",
)

# Confidence by how the place_type was established. These are not tuned
# probabilities -- they are an explicit, auditable ordering of how much each
# kind of evidence deserves to be trusted, in the same spirit as
# knowledge_type_policy.py's profile tables.
_CONFIDENCE_SEED = 0.90        # a human curator wrote this type down
_CONFIDENCE_PRIMARY_TYPE = 0.95  # Google's own primaryType for the place
_CONFIDENCE_SECONDARY_TYPE = 0.80  # merely present in Google's types[]
_CONFIDENCE_NAME_RULE = 0.75   # inferred from wording in the name
_CONFIDENCE_LEGACY = 0.70      # reconstructed from the old single-category columns
_CONFIDENCE_UNKNOWN = 0.30     # nothing established; the honest 'other'

# The place_type assignment is by definition the most defining thing about a
# place, so it anchors the relevance scale at the top.
_PRIMARY_PLACE_TYPE_RELEVANCE = 100


@dataclass(frozen=True)
class ProposedCategory:
    """One category this place should be assigned, before it is persisted."""

    kind: str      # catalog.KIND_THEME | catalog.KIND_PLACE_TYPE
    slug: str
    relevance: int  # 0-100, for THIS place
    confidence: float  # 0-1
    is_primary: bool   # at most one True per kind
    source: str        # one of ASSIGNMENT_SOURCES
    rationale: str | None = None


# --- Google Places type -> place_type ----------------------------------------
#
# Covers every key in categories.GOOGLE_TYPE_MAP (which doubles as Google's
# `includedTypes` request allowlist, so those are the types Nearby Search can
# return as primaryType) PLUS types that commonly appear in a place's
# secondary `types[]` array. An unmapped type is not an error -- resolution
# simply falls through, exactly like classify()'s existing behaviour.

GOOGLE_TYPE_TO_PLACE_TYPE: dict[str, str] = {
    # Trail / outdoors
    "bridge": "bridge",
    "hiking_area": "trailhead",
    "campground": "campsite",
    "rv_park": "rv_park",
    # Nature
    "mountain_peak": "mountain_peak",
    "lake": "lake",
    "river": "river",
    "beach": "beach",
    "island": "island",
    "woods": "forest",
    "forest": "forest",
    "nature_preserve": "nature_reserve",
    "national_park": "national_park",
    "state_park": "state_park",
    "park": "city_park",
    "garden": "garden",
    "botanical_garden": "garden",
    "wildlife_park": "wildlife_reserve",
    "wildlife_refuge": "wildlife_reserve",
    "zoo": "zoo",
    "aquarium": "aquarium",
    # Scenic
    "scenic_spot": "viewpoint",
    "observation_deck": "viewpoint",
    "visitor_center": "visitor_centre",
    "tourist_information_center": "tourist_office",
    "plaza": "plaza",
    # Religious
    "church": "church",
    "mosque": "mosque",
    "synagogue": "synagogue",
    "hindu_temple": "temple",
    # Google's `buddhist_temple` covers both temples and gompas; `temple` is
    # the safer of the two, since `monastery` additionally asserts that monks
    # live there. A name rule below promotes real gompas/monasteries.
    "buddhist_temple": "temple",
    "shinto_shrine": "shrine",
    "place_of_worship": "shrine",
    # Culture & heritage
    "museum": "museum",
    "art_museum": "museum",
    "history_museum": "museum",
    "art_gallery": "gallery",
    "historical_place": "historical_site",
    "historical_landmark": "historical_site",
    "cultural_landmark": "landmark",
    "monument": "monument",
    "tourist_attraction": "landmark",
    "performing_arts_theater": "theatre",
    "opera_house": "opera_house",
    "concert_hall": "concert_hall",
    "movie_theater": "cinema",
    "amusement_park": "amusement_park",
    "water_park": "water_park",
    "casino": "casino",
    "cemetery": "cemetery",
    # Food & drink
    "cafe": "cafe",
    "coffee_shop": "cafe",
    "tea_house": "tea_stall",
    "restaurant": "restaurant",
    "bakery": "bakery",
    "bar": "bar",
    "pub": "pub",
    "night_club": "nightclub",
    "brewery": "brewery",
    "winery": "winery",
    "market": "market",
    "supermarket": "supermarket",
    "grocery_store": "supermarket",
    "convenience_store": "supermarket",
    # Lodging
    "lodging": "guesthouse",
    "hotel": "hotel",
    "guest_house": "guesthouse",
    "hostel": "hostel",
    "resort_hotel": "resort",
    "motel": "hotel",
    "bed_and_breakfast": "guesthouse",
    "cottage": "guesthouse",
    "farmstay": "homestay",
    # Shopping
    "shopping_mall": "mall",
    "department_store": "mall",
    "sporting_goods_store": "gear_shop",
    "book_store": "bookstore",
    "gift_shop": "gift_shop",
    "clothing_store": "shop",
    "store": "shop",
    "home_goods_store": "shop",
    # Health
    "hospital": "hospital",
    "doctor": "clinic",
    "dentist": "clinic",
    "medical_lab": "clinic",
    "pharmacy": "pharmacy",
    "drugstore": "pharmacy",
    # Safety / civic
    "police": "police_post",
    "fire_station": "police_post",
    "embassy": "embassy",
    "courthouse": "courthouse",
    "city_hall": "town_hall",
    "local_government_office": "government_building",
    # Money / post
    "atm": "atm",
    "bank": "bank",
    "post_office": "post_office",
    # Transport
    "airport": "airport",
    "international_airport": "airport",
    "heliport": "helipad",
    "bus_station": "bus_station",
    "bus_stop": "bus_station",
    "train_station": "railway_station",
    "subway_station": "metro_station",
    "light_rail_station": "metro_station",
    "transit_station": "bus_station",
    "ferry_terminal": "ferry_terminal",
    "taxi_stand": "taxi_jeep_stand",
    "marina": "port_marina",
    # Services / education / sport
    "travel_agency": "travel_agency",
    "laundry": "laundry",
    "internet_cafe": "internet_cafe",
    "library": "library",
    "university": "university",
    "school": "school",
    "primary_school": "school",
    "secondary_school": "school",
    "observatory": "observatory",
    "planetarium": "planetarium",
    "stadium": "stadium",
    "sports_complex": "sporting_area",
    "golf_course": "golf_course",
    "gym": "fitness_centre",
    "fitness_center": "fitness_centre",
    "swimming_pool": "pool",
    "ski_resort": "ski_resort",
    "farm": "farm",
}


# --- Curated seed "Type" column -> place_type --------------------------------
#
# Keys match categories.SEED_TYPE_MAP exactly (lowercased), so the two
# vocabularies never drift. Matched case-insensitively -- a spreadsheet's
# casing is a human convention, not an API contract.

SEED_TYPE_TO_PLACE_TYPE: dict[str, str] = {
    "restaurant": "restaurant",
    "cafe / restaurant": "cafe",
    "bakery / food": "bakery",
    "lodge / restaurant": "lodge",
    "upgrade lodge": "lodge",
    "shop": "shop",
    "gift shop": "gift_shop",
    "tour operator": "tour_operator",
    "nightlife": "bar",
    "pub / nightlife": "pub",
    "attraction": "historical_site",
    "cultural site": "temple",
    "airport": "airport",
    "airline office": "airline_office",
    "travel / ticketing": "ticketing_office",
    "landmark / trail orientation": "landmark",
    "hospital / medical": "hospital",
    "bank / atm candidate": "bank",
    "safety / police": "police_post",
    "post office": "post_office",
}


# --- Name-based refinements ---------------------------------------------------
#
# Generalises the single tea-stall rule that already lives in categories.py.
# A rule may only refine place_types listed in `refines` -- so "Everest Bakery
# Cafe" becomes a bakery, but a HOSPITAL with "Cafe" in its name is never
# demoted to one. `refines=None` means the name is decisive enough to apply
# whatever the resolved type was (e.g. an explicit "Base Camp").
#
# Order matters: first match wins, so more specific rules come first.


@dataclass(frozen=True)
class NameRule:
    pattern: re.Pattern[str]
    place_type: str
    refines: frozenset[str] | None


_FOOD_LIKE = frozenset({"cafe", "restaurant", "bakery", "shop", "other", "tea_stall"})
_SHOP_LIKE = frozenset({"shop", "specialty_store", "mall", "gift_shop", "other"})
_LODGING_LIKE = frozenset({"hotel", "guesthouse", "lodge", "hostel", "other", "restaurant"})
_WORSHIP_LIKE = frozenset({"temple", "shrine", "monastery", "other"})
_MEDICAL_LIKE = frozenset({"hospital", "clinic", "pharmacy", "other"})

NAME_RULES: tuple[NameRule, ...] = (
    # Nepal / Himalaya specifics -- these are the places the source inventory
    # had no vocabulary for at all.
    NameRule(re.compile(r"\bbase\s*camp\b", re.I), "base_camp", None),
    NameRule(re.compile(r"\bhigh\s*camp\b", re.I), "high_camp", None),
    NameRule(re.compile(r"\b(gompa|gumba|gonpa)\b", re.I), "gompa", _WORSHIP_LIKE),
    NameRule(re.compile(r"\bmonaster(y|ies)\b", re.I), "monastery", _WORSHIP_LIKE),
    NameRule(re.compile(r"\b(stupa|chorten)\b", re.I), "stupa", _WORSHIP_LIKE),
    NameRule(re.compile(r"\bmani\s+wall\b", re.I), "mani_wall", None),
    NameRule(re.compile(r"\bsuspension\s+bridge\b", re.I), "suspension_bridge", None),
    NameRule(re.compile(r"\b(helipad|heliport|helicopter\s+pad)\b", re.I), "helipad", None),
    NameRule(re.compile(r"\b(rescue\s+post|rescue\s+centre|rescue\s+center)\b", re.I), "rescue_post", None),
    NameRule(re.compile(r"\b(check\s?post|checkpoint|permit\s+office|entry\s+permit)\b", re.I),
             "permit_checkpost", None),
    NameRule(re.compile(r"\btea\s*house\b", re.I), "teahouse", _LODGING_LIKE),
    NameRule(re.compile(r"\btrek(king|kers)?\s+lodge\b", re.I), "trekking_lodge", _LODGING_LIKE),
    NameRule(re.compile(r"\bhomestay\b", re.I), "homestay", _LODGING_LIKE),
    # Health -- worth getting right; these are safety-relevant.
    NameRule(re.compile(r"\baltitude\b.*\b(clinic|aid|centre|center)\b", re.I), "altitude_clinic", None),
    NameRule(re.compile(r"\bhealth\s+(post|centre|center)\b", re.I), "health_post", None),
    NameRule(re.compile(r"\b(pharmac(y|ies)|chemist|medical\s+hall|drug\s+store)\b", re.I),
             "pharmacy", _MEDICAL_LIKE),
    NameRule(re.compile(r"\bclinic\b", re.I), "clinic", _MEDICAL_LIKE),
    # Money
    NameRule(re.compile(r"\b(money\s+exchange|foreign\s+exchange|forex|money\s+changer)\b", re.I),
             "money_exchange", None),
    NameRule(re.compile(r"\batm\b", re.I), "atm", frozenset({"bank", "other"})),
    # Shopping -- the Thamel case: a "shop" whose name says trekking gear is a
    # gear shop, which is a materially different thing to a guide.
    NameRule(re.compile(r"\b(trek(king)?|mountaineer(ing)?|outdoor|gear|equipment)\b", re.I),
             "gear_shop", _SHOP_LIKE),
    NameRule(re.compile(r"\b(handicraft|handmade|craft|thanka|thangka|pashmina)\b", re.I),
             "handicraft_shop", _SHOP_LIKE),
    # Food -- the existing tea-stall rule, preserved verbatim in spirit.
    NameRule(re.compile(r"\btea\b", re.I), "tea_stall", _FOOD_LIKE),
    NameRule(re.compile(r"\b(bakery|bakehouse|patisserie|bake\s*house)\b", re.I), "bakery", _FOOD_LIKE),
    # Practical
    NameRule(re.compile(r"\blaundry\b", re.I), "laundry", None),
    NameRule(re.compile(r"\b(view\s?point|lookout)\b", re.I), "viewpoint",
             frozenset({"other", "landmark", "scenic_spot"})),
)


# --- Resolution ---------------------------------------------------------------


def _resolve_place_type(
    primary_type: str | None,
    types: list[str] | None,
    seed_type: str | None,
    legacy_subcategory: str | None,
) -> tuple[str, float, str]:
    """(place_type_slug, confidence, source). Never fails -- falls back to
    the honest 'other', exactly like categories.classify() does today."""
    if seed_type:
        slug = SEED_TYPE_TO_PLACE_TYPE.get(seed_type.strip().lower())
        if slug:
            return slug, _CONFIDENCE_SEED, "seed_type"

    if primary_type:
        slug = GOOGLE_TYPE_TO_PLACE_TYPE.get(primary_type)
        if slug:
            return slug, _CONFIDENCE_PRIMARY_TYPE, "google_type"
        if primary_type in catalog_area_geocode_types():
            return catalog.AREA_PLACE_TYPE, _CONFIDENCE_PRIMARY_TYPE, "google_type"

    for candidate in types or []:
        slug = GOOGLE_TYPE_TO_PLACE_TYPE.get(candidate)
        if slug:
            return slug, _CONFIDENCE_SECONDARY_TYPE, "google_type"
        if candidate in catalog_area_geocode_types():
            return catalog.AREA_PLACE_TYPE, _CONFIDENCE_SECONDARY_TYPE, "google_type"

    # Nothing from the providers -- fall back to whatever the old single
    # columns already said, so pre-existing rows classify from what they know
    # rather than all collapsing to 'other'.
    if legacy_subcategory:
        slug = catalog.LEGACY_SUBCATEGORY_TO_PLACE_TYPE.get(legacy_subcategory)
        if slug:
            return slug, _CONFIDENCE_LEGACY, "google_type"

    return catalog.OTHER_PLACE_TYPE, _CONFIDENCE_UNKNOWN, "google_type"


def catalog_area_geocode_types() -> frozenset[str]:
    """Geocoding API types that mean "this is an area, not a venue".

    Imported lazily-by-function rather than at module scope to avoid a circular
    import: categories.py is the older module and does not know about this one.
    """
    from app.services.places import categories

    return frozenset(categories.GEOCODE_AREA_TYPE_MAP)


def _apply_name_rule(place_type: str, name: str | None) -> tuple[str, bool]:
    """(place_type, refined). Applies the first matching name rule whose
    `refines` set allows it."""
    if not name:
        return place_type, False
    for rule in NAME_RULES:
        if rule.refines is not None and place_type not in rule.refines:
            continue
        if rule.pattern.search(name):
            if rule.place_type == place_type:
                return place_type, False
            return rule.place_type, True
    return place_type, False


def classify_categories(
    *,
    primary_type: str | None = None,
    types: list[str] | None = None,
    name: str | None = None,
    seed_type: str | None = None,
    legacy_subcategory: str | None = None,
) -> list[ProposedCategory]:
    """The full deterministic classification for one already-identified place.

    Returns the place_type assignment first (always exactly one, always
    primary), then the themes it implies, most relevant first. The single
    highest-relevance theme is marked primary so the pair
    (primary theme, primary place_type) mirrors the legacy
    (category, subcategory) pair.
    """
    place_type, confidence, source = _resolve_place_type(
        primary_type, types, seed_type, legacy_subcategory
    )
    place_type, refined = _apply_name_rule(place_type, name)
    if refined:
        confidence = _CONFIDENCE_NAME_RULE
        source = "name_rule"

    definition = catalog.PLACE_TYPES_BY_SLUG.get(place_type)
    if definition is None:
        # A rule pointed at a slug the catalog does not have. Treat as
        # unclassified rather than writing a dangling assignment.
        definition = catalog.PLACE_TYPES_BY_SLUG[catalog.OTHER_PLACE_TYPE]
        place_type, confidence, source = (
            catalog.OTHER_PLACE_TYPE,
            _CONFIDENCE_UNKNOWN,
            "google_type",
        )

    proposals = [
        ProposedCategory(
            kind=catalog.KIND_PLACE_TYPE,
            slug=place_type,
            relevance=_PRIMARY_PLACE_TYPE_RELEVANCE,
            confidence=confidence,
            is_primary=True,
            source=source,
            rationale=_place_type_rationale(source, primary_type, seed_type, name),
        )
    ]

    # Themes the resolved place_type implies. They inherit the place_type's
    # confidence deliberately: the implication itself is certain (a temple IS
    # religious), so the only uncertainty is whether the place_type was right.
    themes = sorted(definition.themes, key=lambda pair: pair[1], reverse=True)
    for index, (theme_slug, relevance) in enumerate(themes):
        if not catalog.exists(catalog.KIND_THEME, theme_slug):
            continue
        proposals.append(
            ProposedCategory(
                kind=catalog.KIND_THEME,
                slug=theme_slug,
                relevance=relevance,
                confidence=confidence,
                is_primary=(index == 0),
                source="rule_implied",
                rationale=f"implied by place type '{definition.display_name}'",
            )
        )
    return proposals


def _place_type_rationale(
    source: str, primary_type: str | None, seed_type: str | None, name: str | None
) -> str:
    if source == "seed_type" and seed_type:
        return f"curated type '{seed_type}'"
    if source == "name_rule" and name:
        return f"name pattern in '{name}'"
    if primary_type:
        return f"Google type '{primary_type}'"
    return "no provider type available"


# --- When is deterministic classification not good enough? --------------------

# Themes that say nothing about what is interesting at a place. A result
# consisting only of these is exactly as uninformative as no result.
_UNINFORMATIVE_THEMES = frozenset({catalog.OTHER_THEME, catalog.AREA_THEME})

# A classified place needs at least this many informative themes. One is
# enough ON PURPOSE, and the reasoning matters for cost: themes are DERIVED
# from the place_type via the catalog, so once the type is confidently known
# the themes are already as good as the vocabulary can make them. Asking a
# model to second-guess "restaurant implies Food & Drink" would spend money
# per place to re-derive something deterministic. The model fallback exists
# for places whose TYPE is unknown, not to embellish ones whose type is not.
MIN_INFORMATIVE_THEMES = 1


def is_weak(proposals: list[ProposedCategory]) -> bool:
    """Should the AI classifier be asked about this place?

    ONE criterion: does this place have anything informative said about it?
    'other' and 'area' don't count, because neither says a thing about what
    is actually interesting somewhere.

    That single test covers every case the rules can produce, which is why
    there is no separate place_type check:
      - 'other'   implies only the 'other' theme        -> 0 informative -> weak
      - an AREA   implies only the 'area' theme         -> 0 informative -> weak
      - 'restaurant' implies Food & Drink               -> 1 informative -> fine
    Crucially it is also stable AFTER a model pass: once Thamel has been
    classified Shopping/Food/Trekking/Nightlife, it stops being weak even
    though it is still structurally an area. A place_type-based test would
    have kept re-selecting it and paying for the same answer forever.
    """
    informative = [
        p
        for p in proposals
        if p.kind == catalog.KIND_THEME and p.slug not in _UNINFORMATIVE_THEMES
    ]
    return len(informative) < MIN_INFORMATIVE_THEMES
