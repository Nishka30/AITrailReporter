"""TrailMind's OWN category vocabulary -- the controlled list every
`location_category_assignments` row must point at.

WHY A CONTROLLED VOCABULARY AT ALL:
A Location can be many things at once ("Nature" AND "Wildlife" AND
"Adventure"), and the whole point of recording that is to rank information
later. Free-text categories make ranking impossible -- "wildlife",
"Wildlife", "wild life" and "fauna" would be four different buckets. So the
catalog is closed: rules pick from it, the AI classifier picks from it (never
inventing), and a human curator picks from it. Adding a category is a
deliberate edit here, not a side effect of classifying one place.

THE TWO KINDS, AND WHY THE SPLIT EARNS ITS KEEP:
  place_type -- what the place literally IS. "Temple", "Waterfall",
                "Teahouse". A place has essentially one of these.
  theme      -- what the place is ABOUT; the kind of interest it serves.
                "Nature", "Wildlife", "Religious", "Practical". A place has
                several.

That split is not invented here -- it is already latent in the two columns
this system extends. `Location.category` has always held theme-shaped values
("Nature", "Food & Drink") and `Location.subcategory` type-shaped ones
("Bridge", "Museum", "Cafe"). Naming the distinction is what makes
multi-category assignment DETERMINISTIC: a place_type declares the themes it
implies, once, here -- so one Google type ("hindu_temple") yields a whole
honest set (Temple + Religious + Culture & Heritage + Historical) with no
model call and no per-place guesswork.

RELATIONSHIP TO `Location.category`/`subcategory` (IMPORTANT):
Those columns are NOT replaced and NOT deprecated. They remain exactly what
they are today, written by exactly the same code. Several load-bearing things
depend on them being single, comparable strings -- area resolution filters on
`category == 'Area'` in SQL, the area reuse radius is keyed off the
subcategory literal, the candidate picker penalises `'Other'` and de-duplicates
by category, and the mobile map-pin icon switches on the category string.
This catalog therefore MIRRORS those values rather than competing with them:
every legacy category string has a theme here with a byte-identical
`display_name`, and every legacy subcategory a place_type. See
LEGACY_CATEGORY_TO_THEME / LEGACY_SUBCATEGORY_TO_PLACE_TYPE at the bottom.

PROVENANCE (`touristlink_id`):
Most rows come from a supplied third-party category inventory ("Touristlink",
565 rows). Its id is kept so a row's origin stays checkable. It is provenance
ONLY -- never a foreign key, never required, and deliberately null for the
categories TrailMind adds. Roughly 350 of that inventory's rows were a
tour-booking product taxonomy ("Half-day Coach Tour", "Passport Info") and
another ~30 were the geographic hierarchy or events; none of those describe a
physical place, so none are here. What that inventory systematically lacked --
practical and safety infrastructure (health, police, water, money, toilets,
charging) and trekking-specific places (teahouse, trailhead, base camp,
rescue post, gear shop) -- is exactly what a guide standing on a trail reports
on, so those are added with `touristlink_id = None`.
"""

from dataclasses import dataclass

# Kind discriminator, stored on both the catalog row and every assignment.
KIND_THEME = "theme"
KIND_PLACE_TYPE = "place_type"
CATEGORY_KINDS = (KIND_THEME, KIND_PLACE_TYPE)


@dataclass(frozen=True)
class ThemeDef:
    """One theme: what a place is ABOUT."""

    slug: str
    display_name: str
    # 0-100, how much this theme generally matters when ranking what to
    # surface about a place. Used as the fallback relevance when nothing
    # location-specific is known, NOT as the assigned relevance itself (see
    # category_rules.py -- a place_type declares a relevance per implied
    # theme, because "Nature" means something different at a waterfall than
    # at a city park).
    default_priority: int
    # Plain-language meaning. Load-bearing, not decoration: this text is what
    # the AI classifier is shown as its vocabulary definition, so an
    # ambiguous line here produces ambiguous classifications.
    description: str
    touristlink_id: int | None = None


@dataclass(frozen=True)
class PlaceTypeDef:
    """One place_type: what a place literally IS, plus the themes it implies."""

    slug: str
    display_name: str
    default_priority: int
    description: str
    # (theme_slug, relevance 0-100). THE deterministic multi-category
    # mechanism: assigning this place_type assigns every theme listed here at
    # the stated relevance. Ordered most-relevant-first purely for
    # readability; nothing depends on the order.
    themes: tuple[tuple[str, int], ...] = ()
    touristlink_id: int | None = None


# --- Themes -----------------------------------------------------------------
#
# The 16 display names that already exist as `Location.category` values are
# reproduced EXACTLY (Trail, Nature, Scenic Spot, Culture & Heritage, Food &
# Drink, Lodging, Shopping, Services, Nightlife, Transport, Health, Finance,
# Safety, Postal, Area, Other) so the primary theme of a Location always
# equals its legacy category string. The rest are new.

THEMES: tuple[ThemeDef, ...] = (
    ThemeDef("trail", "Trail", 85, "On or serving a walking/trekking route itself."),
    ThemeDef("trekking", "Trekking", 90, "Directly relevant to a multi-day trek: route, altitude, resupply, permits."),
    ThemeDef("nature", "Nature", 85, "Natural landscape, terrain or ecosystem."),
    ThemeDef("wildlife", "Wildlife", 80, "Animals, birds or habitat are a main reason to be here."),
    ThemeDef("adventure", "Adventure", 75, "Physically demanding or thrill-seeking activity."),
    ThemeDef("scenic_spot", "Scenic Spot", 80, "Somewhere people go for the view."),
    ThemeDef("photography", "Photography", 60, "Notably worth photographing."),
    ThemeDef("water", "Water", 65, "Water is central: river, lake, sea, spring, falls."),
    ThemeDef("culture_heritage", "Culture & Heritage", 80, "Cultural, artistic or heritage significance."),
    ThemeDef("historical", "Historical", 75, "Significant for its history or age."),
    ThemeDef("religious", "Religious", 75, "A place of worship, pilgrimage or religious meaning."),
    ThemeDef("local_life", "Local Life", 70, "Everyday life of the people who live here."),
    ThemeDef("food_drink", "Food & Drink", 85, "Somewhere to eat or drink."),
    ThemeDef("lodging", "Lodging", 80, "Somewhere to sleep."),
    ThemeDef("shopping", "Shopping", 70, "Somewhere to buy things."),
    ThemeDef("nightlife", "Nightlife", 55, "Evening and night social venues."),
    ThemeDef("transport", "Transport", 75, "Getting to, from or through somewhere."),
    ThemeDef("practical", "Practical", 75, "Solves a traveller's practical need: water, power, toilets, permits, supplies."),
    ThemeDef("health", "Health", 85, "Medical care or health-related facilities."),
    ThemeDef("safety", "Safety", 95, "Bears on whether someone is safe -- hazards, rescue, police."),
    ThemeDef("finance", "Finance", 70, "Money: cash, exchange, banking."),
    ThemeDef("postal", "Postal", 45, "Post and parcels."),
    ThemeDef("services", "Services", 60, "A service business a traveller might need."),
    ThemeDef("entertainment", "Entertainment", 50, "Shows, attractions and amusements."),
    ThemeDef("sport", "Sport", 45, "Sport is played or watched here."),
    ThemeDef("education", "Education", 45, "Learning, science or study."),
    ThemeDef("urban", "Urban", 45, "Characteristically part of a built-up townscape."),
    ThemeDef("family", "Family", 50, "Particularly suited to visiting with children."),
    # Mirrors the reverse-geocoded AREA concept so an area Location's primary
    # theme matches its legacy category. Low priority: "this is an area" says
    # little about what is interesting there.
    ThemeDef("area", "Area", 40, "A named neighbourhood, village, town or district rather than a single venue."),
    # The honest "we could not say", mirroring DEFAULT_CATEGORY. Never a
    # reason to drop a place.
    ThemeDef("other", "Other", 10, "Nothing specific established about what this place is."),
)


# --- Place types ------------------------------------------------------------

PLACE_TYPES: tuple[PlaceTypeDef, ...] = (
    # --- Trail & trekking ---------------------------------------------------
    PlaceTypeDef("trail", "Trail", 90, "A walking or trekking route.",
                 (("trail", 100), ("trekking", 95), ("nature", 80), ("adventure", 75)), 34),
    PlaceTypeDef("trailhead", "Trailhead", 88, "Where a trail begins or is entered.",
                 (("trail", 95), ("trekking", 90), ("practical", 70))),
    PlaceTypeDef("suspension_bridge", "Suspension Bridge", 85, "A footbridge carrying a trail over a river or gorge.",
                 (("trail", 90), ("trekking", 85), ("adventure", 75), ("scenic_spot", 65))),
    PlaceTypeDef("bridge", "Bridge", 70, "A road or foot bridge.",
                 (("trail", 70), ("transport", 70), ("historical", 40)), 140),
    PlaceTypeDef("mountain_pass", "Mountain Pass", 92, "A saddle or col a route crosses.",
                 (("trekking", 95), ("nature", 85), ("adventure", 80), ("safety", 70), ("scenic_spot", 75)), 234),
    PlaceTypeDef("base_camp", "Base Camp", 90, "A staging camp below a peak.",
                 (("trekking", 95), ("adventure", 85), ("lodging", 70))),
    PlaceTypeDef("high_camp", "High Camp", 88, "A high-altitude camp above base camp.",
                 (("trekking", 95), ("adventure", 85), ("lodging", 65), ("safety", 70))),
    PlaceTypeDef("acclimatisation_point", "Acclimatisation Point", 88,
                 "Where trekkers stop to adjust to altitude.",
                 (("trekking", 90), ("health", 85), ("safety", 80))),
    PlaceTypeDef("river_crossing", "River Crossing", 85, "A ford or crossing point on a route.",
                 (("trail", 85), ("trekking", 85), ("safety", 80), ("water", 70))),
    PlaceTypeDef("rest_stop", "Rest Stop", 70, "A recognised place to pause on a route.",
                 (("trail", 70), ("practical", 75), ("food_drink", 55))),
    PlaceTypeDef("campsite", "Campsite", 78, "Somewhere to pitch a tent.",
                 (("lodging", 80), ("trekking", 75), ("nature", 70)), 100),
    PlaceTypeDef("rv_park", "RV Park", 55, "Vehicle camping ground.",
                 (("lodging", 70), ("transport", 50)), 278),
    PlaceTypeDef("viewpoint", "Viewpoint", 88, "A spot specifically for the view.",
                 (("scenic_spot", 100), ("photography", 85), ("nature", 70)), 215),
    PlaceTypeDef("scenic_drive", "Scenic Drive", 70, "A road travelled for its views.",
                 (("scenic_spot", 80), ("nature", 70), ("transport", 65)), 209),

    # --- Hazards ------------------------------------------------------------
    # TrailMind exists largely to report on these. Absent from the source
    # inventory entirely, which is a sightseeing catalogue.
    PlaceTypeDef("landslide_zone", "Landslide Zone", 95, "A slope known to slide or shed debris.",
                 (("safety", 100), ("trail", 75))),
    PlaceTypeDef("avalanche_zone", "Avalanche Zone", 95, "Terrain with known avalanche risk.",
                 (("safety", 100), ("trekking", 80))),
    PlaceTypeDef("rockfall_zone", "Rockfall Zone", 93, "A section exposed to falling rock.",
                 (("safety", 95), ("trail", 75))),
    PlaceTypeDef("flood_prone_area", "Flood-Prone Area", 90, "Ground that floods or washes out.",
                 (("safety", 95), ("water", 70))),
    PlaceTypeDef("crevasse_area", "Crevasse Area", 93, "Glaciated ground with crevasse risk.",
                 (("safety", 100), ("trekking", 85))),

    # --- Mountains & terrain ------------------------------------------------
    PlaceTypeDef("mountain_peak", "Mountain Peak", 90, "A summit.",
                 (("nature", 95), ("trekking", 90), ("scenic_spot", 90), ("adventure", 80)), 32),
    PlaceTypeDef("mountain_range", "Mountain Range", 80, "A connected range of mountains.",
                 (("nature", 90), ("scenic_spot", 85), ("trekking", 80)), 79),
    PlaceTypeDef("ridge", "Ridge", 78, "A ridgeline.",
                 (("nature", 80), ("trekking", 85), ("scenic_spot", 75)), 225),
    PlaceTypeDef("hill", "Hill", 65, "A hill.", (("nature", 80), ("scenic_spot", 75)), 182),
    PlaceTypeDef("hill_station", "Hill Station", 70, "An upland town visited for its climate and views.",
                 (("nature", 80), ("scenic_spot", 80), ("lodging", 60)), 105),
    PlaceTypeDef("valley", "Valley", 78, "A valley.", (("nature", 85), ("scenic_spot", 80)), 183),
    PlaceTypeDef("glacier", "Glacier", 85, "A glacier.",
                 (("nature", 90), ("scenic_spot", 85), ("adventure", 80), ("trekking", 75)), 77),
    PlaceTypeDef("volcano", "Volcano", 82, "A volcano.",
                 (("nature", 90), ("scenic_spot", 85), ("adventure", 70)), 214),
    PlaceTypeDef("canyon", "Canyon", 80, "A canyon or gorge.",
                 (("nature", 85), ("scenic_spot", 85), ("adventure", 75)), 73),
    PlaceTypeDef("cave", "Cave", 75, "A cave.",
                 (("nature", 80), ("adventure", 75), ("scenic_spot", 65)), 33),
    PlaceTypeDef("desert", "Desert", 72, "Desert terrain.",
                 (("nature", 80), ("scenic_spot", 75), ("adventure", 70)), 74),
    PlaceTypeDef("geologic_feature", "Geologic Feature", 70, "A notable rock or landform.",
                 (("nature", 80), ("scenic_spot", 70)), 239),
    PlaceTypeDef("natural_feature", "Natural Feature", 68, "A natural landmark not otherwise typed.",
                 (("nature", 80), ("scenic_spot", 70)), 75),

    # --- Water --------------------------------------------------------------
    PlaceTypeDef("waterfall", "Waterfall", 85, "A waterfall.",
                 (("nature", 90), ("scenic_spot", 90), ("water", 85), ("photography", 75)), 70),
    PlaceTypeDef("lake", "Lake", 80, "A lake.",
                 (("nature", 85), ("water", 85), ("scenic_spot", 80)), 31),
    PlaceTypeDef("river", "River", 80, "A river.",
                 (("nature", 85), ("water", 85), ("scenic_spot", 70)), 101),
    PlaceTypeDef("hot_spring", "Hot Spring", 75, "A natural hot spring.",
                 (("nature", 75), ("water", 80), ("health", 60)), 30),
    PlaceTypeDef("beach", "Beach", 75, "A beach.",
                 (("water", 85), ("nature", 75), ("scenic_spot", 70), ("family", 60)), 29),
    PlaceTypeDef("island", "Island", 75, "An island.",
                 (("nature", 80), ("scenic_spot", 80), ("water", 75)), 199),
    PlaceTypeDef("coastal_area", "Coastal Area", 70, "A stretch of coast.",
                 (("water", 80), ("nature", 75), ("scenic_spot", 70)), 76),
    PlaceTypeDef("fjord", "Fjord", 80, "A fjord.",
                 (("nature", 85), ("scenic_spot", 85), ("water", 80)), 242),
    PlaceTypeDef("strait", "Strait", 62, "A strait.", (("water", 75), ("nature", 70)), 241),
    PlaceTypeDef("backwater", "Backwater", 65, "Calm inland waterways.",
                 (("water", 75), ("nature", 70), ("scenic_spot", 65)), 181),
    PlaceTypeDef("wetland", "Wetland", 72, "Marsh, bog or wetland.",
                 (("nature", 80), ("wildlife", 80)), 227),
    PlaceTypeDef("dam", "Dam", 58, "A dam or reservoir wall.",
                 (("water", 70), ("urban", 55), ("scenic_spot", 55)), 102),
    PlaceTypeDef("canal", "Canal", 55, "A canal.", (("water", 70), ("urban", 50)), 207),
    PlaceTypeDef("pier", "Pier", 58, "A pier or jetty.",
                 (("water", 70), ("scenic_spot", 60), ("transport", 55)), 163),
    PlaceTypeDef("port_marina", "Port or Marina", 65, "A harbour for boats.",
                 (("transport", 75), ("water", 75)), 164),
    PlaceTypeDef("lighthouse", "Lighthouse", 70, "A lighthouse.",
                 (("scenic_spot", 80), ("historical", 65), ("water", 65)), 165),

    # --- Protected land & wildlife ------------------------------------------
    PlaceTypeDef("national_park", "National Park", 90, "A national park.",
                 (("nature", 95), ("wildlife", 90), ("trekking", 80), ("adventure", 70)), 71),
    PlaceTypeDef("state_park", "State Park", 75, "A state or provincial park.",
                 (("nature", 85), ("wildlife", 70), ("trekking", 70)), 36),
    PlaceTypeDef("nature_reserve", "Nature Reserve", 82, "Protected natural land.",
                 (("nature", 90), ("wildlife", 85)), 226),
    PlaceTypeDef("wildlife_reserve", "Wildlife Reserve", 85, "Land protected for its animals.",
                 (("wildlife", 95), ("nature", 90)), 103),
    PlaceTypeDef("bird_sanctuary", "Bird Sanctuary", 78, "Protected bird habitat.",
                 (("wildlife", 90), ("nature", 85), ("photography", 70)), 218),
    PlaceTypeDef("marine_sanctuary", "Marine Sanctuary", 75, "Protected marine habitat.",
                 (("wildlife", 85), ("nature", 80), ("water", 80)), 217),
    PlaceTypeDef("forest", "Forest", 80, "Forest or woodland.",
                 (("nature", 90), ("wildlife", 80), ("trekking", 70), ("adventure", 65)), 35),
    PlaceTypeDef("national_forest", "National Forest", 78, "A protected national forest.",
                 (("nature", 90), ("wildlife", 80), ("trekking", 70)), 161),
    PlaceTypeDef("notable_tree", "Notable Tree", 55, "A individually notable tree.",
                 (("nature", 70), ("scenic_spot", 60), ("photography", 60)), 269),
    PlaceTypeDef("zoo", "Zoo", 70, "A zoo or wildlife park.",
                 (("wildlife", 80), ("family", 75), ("entertainment", 60)), 169),
    PlaceTypeDef("aquarium", "Aquarium", 68, "An aquarium.",
                 (("wildlife", 75), ("family", 75), ("water", 60), ("entertainment", 55)), 167),

    # --- Parks & gardens ----------------------------------------------------
    PlaceTypeDef("garden", "Garden", 68, "A cultivated garden.",
                 (("nature", 75), ("scenic_spot", 70), ("urban", 60), ("family", 60)), 157),
    PlaceTypeDef("city_park", "City Park", 65, "An urban park.",
                 (("nature", 70), ("urban", 70), ("family", 70)), 40),
    PlaceTypeDef("picnic_spot", "Picnic Spot", 60, "A recognised picnic place.",
                 (("nature", 70), ("family", 75), ("scenic_spot", 60)), 232),
    PlaceTypeDef("recreational_area", "Recreational Area", 58, "General recreation ground.",
                 (("nature", 65), ("family", 65), ("sport", 55)), 220),

    # --- Religious ----------------------------------------------------------
    PlaceTypeDef("temple", "Temple", 85, "A Hindu or Buddhist temple.",
                 (("religious", 95), ("culture_heritage", 90), ("historical", 70)), 144),
    PlaceTypeDef("monastery", "Monastery", 85, "A monastery.",
                 (("religious", 95), ("culture_heritage", 90), ("historical", 75), ("scenic_spot", 55)), 146),
    PlaceTypeDef("gompa", "Gompa", 85, "A Tibetan Buddhist monastery or temple.",
                 (("religious", 95), ("culture_heritage", 90), ("local_life", 70))),
    PlaceTypeDef("stupa", "Stupa", 83, "A stupa or chorten.",
                 (("religious", 95), ("culture_heritage", 90), ("historical", 70), ("photography", 60))),
    PlaceTypeDef("mani_wall", "Mani Wall", 70, "A carved prayer-stone wall beside a trail.",
                 (("religious", 85), ("culture_heritage", 80), ("trail", 60))),
    PlaceTypeDef("church", "Church", 80, "A church.",
                 (("religious", 95), ("culture_heritage", 85), ("historical", 70)), 145),
    PlaceTypeDef("mosque", "Mosque", 80, "A mosque.",
                 (("religious", 95), ("culture_heritage", 85), ("historical", 65)), 143),
    PlaceTypeDef("synagogue", "Synagogue", 80, "A synagogue.",
                 (("religious", 95), ("culture_heritage", 85), ("historical", 70)), 178),
    PlaceTypeDef("gurdwara", "Gurdwara", 80, "A gurdwara.",
                 (("religious", 95), ("culture_heritage", 85)), 176),
    PlaceTypeDef("shrine", "Shrine", 75, "A shrine.",
                 (("religious", 90), ("culture_heritage", 80)), 177),
    PlaceTypeDef("meditation_centre", "Meditation Centre", 65, "A meditation or retreat centre.",
                 (("religious", 75), ("health", 60)), 238),
    PlaceTypeDef("cemetery", "Cemetery", 60, "A cemetery or burial ground.",
                 (("culture_heritage", 70), ("historical", 65)), 198),
    PlaceTypeDef("tomb", "Tomb", 70, "A tomb or mausoleum.",
                 (("historical", 80), ("culture_heritage", 80)), 262),

    # --- Culture, heritage & history ----------------------------------------
    PlaceTypeDef("museum", "Museum", 85, "A museum.",
                 (("culture_heritage", 95), ("education", 80), ("historical", 75)), 25),
    PlaceTypeDef("gallery", "Gallery", 72, "An art gallery.",
                 (("culture_heritage", 85), ("urban", 50)), 204),
    PlaceTypeDef("historical_site", "Historical Site", 85, "A site of historical significance.",
                 (("historical", 95), ("culture_heritage", 90)), 69),
    PlaceTypeDef("heritage_site", "Heritage Site", 88, "A recognised heritage site.",
                 (("historical", 95), ("culture_heritage", 95)), 268),
    PlaceTypeDef("archaeological_site", "Archaeological Site", 80, "An archaeological site.",
                 (("historical", 90), ("culture_heritage", 85), ("education", 60)), 264),
    PlaceTypeDef("ruins", "Ruins", 78, "Ruins.",
                 (("historical", 90), ("culture_heritage", 80), ("scenic_spot", 60)), 147),
    PlaceTypeDef("fort", "Fort", 80, "A fort or fortress.",
                 (("historical", 90), ("culture_heritage", 85), ("scenic_spot", 65)), 106),
    PlaceTypeDef("palace", "Palace", 82, "A palace.",
                 (("historical", 90), ("culture_heritage", 90), ("scenic_spot", 65)), 107),
    PlaceTypeDef("castle", "Castle", 82, "A castle.",
                 (("historical", 90), ("culture_heritage", 90)), 202),
    PlaceTypeDef("monument", "Monument", 78, "A monument.",
                 (("culture_heritage", 85), ("historical", 80), ("scenic_spot", 60)), 148),
    PlaceTypeDef("landmark", "Landmark", 80, "A recognised landmark.",
                 (("scenic_spot", 85), ("culture_heritage", 70)), 249),
    PlaceTypeDef("historic_house", "Historic House", 70, "A preserved historic house.",
                 (("historical", 80), ("culture_heritage", 75)), 201),
    PlaceTypeDef("battlefield", "Battlefield", 70, "A historic battlefield.",
                 (("historical", 85), ("culture_heritage", 70)), 149),
    PlaceTypeDef("pyramid", "Pyramid", 85, "A pyramid.",
                 (("historical", 95), ("culture_heritage", 90)), 150),
    PlaceTypeDef("petroglyph", "Petroglyph Site", 72, "Rock art or carvings.",
                 (("historical", 85), ("culture_heritage", 80)), 231),
    PlaceTypeDef("ancient_wall", "Ancient Wall", 72, "A surviving ancient wall.",
                 (("historical", 85), ("culture_heritage", 80)), 266),
    PlaceTypeDef("megalithic_site", "Megalithic Site", 72, "Standing stones or megaliths.",
                 (("historical", 85), ("culture_heritage", 80)), 267),
    PlaceTypeDef("cliff_dwelling", "Cliff Dwelling", 75, "Cliff or cave dwellings.",
                 (("historical", 85), ("culture_heritage", 80)), 265),
    PlaceTypeDef("ghost_town", "Ghost Town", 68, "An abandoned settlement.",
                 (("historical", 75), ("culture_heritage", 65), ("scenic_spot", 55)), 233),
    PlaceTypeDef("gateway", "Gateway", 65, "A ceremonial gate or arch.",
                 (("historical", 75), ("culture_heritage", 70)), 263),
    PlaceTypeDef("clock_tower", "Clock Tower", 62, "A clock tower.",
                 (("historical", 70), ("culture_heritage", 65), ("urban", 55)), 280),
    PlaceTypeDef("sculpture", "Sculpture", 58, "A public sculpture.",
                 (("culture_heritage", 70), ("urban", 50)), 151),
    PlaceTypeDef("fountain", "Fountain", 52, "A public fountain.",
                 (("urban", 60), ("culture_heritage", 50)), 154),
    PlaceTypeDef("plaza", "Plaza or Square", 70, "A public square.",
                 (("urban", 75), ("local_life", 70), ("culture_heritage", 65)), 153),
    PlaceTypeDef("famous_street", "Famous Street", 75, "A street known in its own right.",
                 (("local_life", 85), ("urban", 80), ("culture_heritage", 60), ("shopping", 60)), 216),
    PlaceTypeDef("roadside_attraction", "Roadside Attraction", 55, "A quirky stop by the road.",
                 (("scenic_spot", 65), ("entertainment", 55)), 637),

    # --- Lodging ------------------------------------------------------------
    PlaceTypeDef("teahouse", "Teahouse", 92,
                 "A trail teahouse providing both meals and beds to trekkers.",
                 (("lodging", 95), ("trekking", 95), ("food_drink", 90), ("local_life", 75))),
    PlaceTypeDef("trekking_lodge", "Trekking Lodge", 90, "A lodge serving trekkers on a route.",
                 (("lodging", 95), ("trekking", 95), ("food_drink", 70))),
    PlaceTypeDef("mountain_hut", "Mountain Hut", 85, "A basic shelter hut in the mountains.",
                 (("lodging", 90), ("trekking", 90), ("safety", 70))),
    PlaceTypeDef("hotel", "Hotel", 78, "A hotel.", (("lodging", 100), ("practical", 60)), 85),
    PlaceTypeDef("guesthouse", "Guesthouse", 78, "A guesthouse.",
                 (("lodging", 95), ("local_life", 60)), 273),
    PlaceTypeDef("lodge", "Lodge", 75, "A lodge.", (("lodging", 90),), 281),
    PlaceTypeDef("hostel", "Hostel", 70, "A hostel.", (("lodging", 85),), 245),
    PlaceTypeDef("homestay", "Homestay", 75, "Staying in a family home.",
                 (("lodging", 85), ("local_life", 85)), 272),
    PlaceTypeDef("resort", "Resort", 70, "A resort.",
                 (("lodging", 95), ("entertainment", 50)), 104),
    PlaceTypeDef("apartment", "Apartment", 55, "A rentable apartment.", (("lodging", 70),), 271),

    # --- Food & drink -------------------------------------------------------
    PlaceTypeDef("restaurant", "Restaurant", 80, "A restaurant.", (("food_drink", 100),), 12),
    PlaceTypeDef("cafe", "Cafe", 75, "A cafe or coffee house.",
                 (("food_drink", 95), ("practical", 50)), 160),
    PlaceTypeDef("tea_stall", "Tea Stall", 72, "A small roadside or trailside tea stall.",
                 (("food_drink", 90), ("local_life", 80))),
    PlaceTypeDef("bakery", "Bakery", 70, "A bakery.", (("food_drink", 85),)),
    PlaceTypeDef("bar", "Bar", 60, "A bar.", (("nightlife", 90), ("food_drink", 70)), 155),
    PlaceTypeDef("pub", "Pub", 60, "A pub.", (("nightlife", 90), ("food_drink", 70))),
    PlaceTypeDef("brewery", "Brewery", 58, "A brewery.",
                 (("food_drink", 75), ("nightlife", 70)), 253),
    PlaceTypeDef("winery", "Winery", 62, "A winery.",
                 (("food_drink", 75), ("nightlife", 50)), 170),
    PlaceTypeDef("market", "Market", 80, "A market.",
                 (("shopping", 95), ("local_life", 90), ("food_drink", 80)), 159),
    PlaceTypeDef("supermarket", "Supermarket", 68, "A supermarket or general store.",
                 (("shopping", 80), ("practical", 75), ("food_drink", 70))),

    # --- Shopping -----------------------------------------------------------
    PlaceTypeDef("gear_shop", "Gear Shop", 85, "Trekking and outdoor equipment.",
                 (("trekking", 95), ("shopping", 90), ("practical", 85))),
    PlaceTypeDef("handicraft_shop", "Handicraft Shop", 70, "Local crafts and handmade goods.",
                 (("shopping", 80), ("local_life", 85), ("culture_heritage", 70))),
    PlaceTypeDef("gift_shop", "Gift Shop", 60, "A gift or souvenir shop.",
                 (("shopping", 80), ("local_life", 60))),
    PlaceTypeDef("shop", "Shop", 60, "A general shop.", (("shopping", 85),)),
    PlaceTypeDef("mall", "Mall", 62, "A shopping mall.",
                 (("shopping", 90), ("urban", 60)), 44),
    PlaceTypeDef("bookstore", "Bookstore", 55, "A bookshop.",
                 (("shopping", 60), ("education", 50)), 158),
    PlaceTypeDef("specialty_store", "Specialty Store", 58, "A specialist retailer.",
                 (("shopping", 75),), 257),

    # --- Health -------------------------------------------------------------
    PlaceTypeDef("hospital", "Hospital", 95, "A hospital.",
                 (("health", 100), ("safety", 90), ("practical", 85))),
    PlaceTypeDef("clinic", "Clinic", 90, "A clinic.",
                 (("health", 95), ("safety", 80), ("practical", 80))),
    PlaceTypeDef("health_post", "Health Post", 90, "A basic rural health post.",
                 (("health", 95), ("safety", 80), ("practical", 85))),
    PlaceTypeDef("altitude_clinic", "Altitude Clinic", 95,
                 "A clinic specifically treating altitude sickness.",
                 (("health", 100), ("trekking", 90), ("safety", 95))),
    PlaceTypeDef("pharmacy", "Pharmacy", 85, "A pharmacy.",
                 (("health", 90), ("practical", 85))),

    # --- Safety & rescue ----------------------------------------------------
    PlaceTypeDef("police_post", "Police Post", 90, "A police station or post.",
                 (("safety", 100), ("practical", 80))),
    PlaceTypeDef("rescue_post", "Rescue Post", 93, "A mountain rescue base.",
                 (("safety", 100), ("trekking", 85))),
    PlaceTypeDef("helipad", "Helipad", 88, "A helicopter landing point.",
                 (("safety", 95), ("transport", 85), ("trekking", 80))),
    PlaceTypeDef("permit_checkpost", "Permit Checkpost", 90,
                 "Where trekking permits or park entry are checked.",
                 (("practical", 95), ("trekking", 90), ("safety", 60))),

    # --- Money & post -------------------------------------------------------
    PlaceTypeDef("atm", "ATM", 88, "A cash machine.",
                 (("finance", 95), ("practical", 90))),
    PlaceTypeDef("bank", "Bank", 80, "A bank branch.",
                 (("finance", 95), ("practical", 80))),
    PlaceTypeDef("money_exchange", "Money Exchange", 82, "A currency exchange.",
                 (("finance", 90), ("practical", 85))),
    PlaceTypeDef("post_office", "Post Office", 60, "A post office.",
                 (("postal", 95), ("practical", 60))),

    # --- Practical infrastructure -------------------------------------------
    PlaceTypeDef("drinking_water", "Drinking Water", 90, "A safe drinking-water point.",
                 (("practical", 95), ("trekking", 90), ("health", 80), ("water", 60))),
    PlaceTypeDef("charging_point", "Charging Point", 85, "Somewhere to charge devices.",
                 (("practical", 90), ("trekking", 85))),
    PlaceTypeDef("wifi_spot", "WiFi Spot", 80, "Somewhere with internet access.",
                 (("practical", 85), ("trekking", 75))),
    PlaceTypeDef("public_toilet", "Public Toilet", 80, "A public toilet.",
                 (("practical", 90),)),
    PlaceTypeDef("laundry", "Laundry", 65, "A laundry service.",
                 (("practical", 80), ("services", 70))),
    PlaceTypeDef("internet_cafe", "Internet Cafe", 65, "An internet cafe.",
                 (("practical", 80), ("services", 70)), 14),

    # --- Services -----------------------------------------------------------
    PlaceTypeDef("tourist_office", "Tourist Office", 75, "An official tourist information office.",
                 (("services", 85), ("practical", 75)), 15),
    PlaceTypeDef("visitor_centre", "Visitor Centre", 72, "A park or site visitor centre.",
                 (("services", 80), ("practical", 70), ("education", 60), ("scenic_spot", 50)), 210),
    PlaceTypeDef("tour_operator", "Tour Operator", 72, "A trekking or tour agency.",
                 (("services", 85), ("trekking", 70)), 108),
    PlaceTypeDef("travel_agency", "Travel Agency", 65, "A travel agency.",
                 (("services", 80), ("practical", 65)), 109),
    PlaceTypeDef("porter_service", "Porter Service", 85, "Porters and guides for hire.",
                 (("services", 90), ("trekking", 95))),
    PlaceTypeDef("embassy", "Embassy", 70, "An embassy or consulate.",
                 (("services", 75), ("practical", 70), ("safety", 60)), 16),
    PlaceTypeDef("community_centre", "Community Centre", 55, "A community hall or centre.",
                 (("local_life", 70), ("services", 55)), 175),
    PlaceTypeDef("farm", "Farm", 60, "A working farm.",
                 (("local_life", 75), ("nature", 60), ("food_drink", 60)), 235),

    # --- Transport ----------------------------------------------------------
    PlaceTypeDef("airport", "Airport", 90, "An airport or airstrip.",
                 (("transport", 100), ("practical", 85)), 80),
    PlaceTypeDef("airline_office", "Airline Office", 65, "An airline ticket office.",
                 (("transport", 80), ("services", 70), ("practical", 65))),
    PlaceTypeDef("ticketing_office", "Ticketing Office", 65, "A travel ticketing office.",
                 (("transport", 80), ("services", 75), ("practical", 70))),
    PlaceTypeDef("bus_station", "Bus Station", 80, "A bus station or stand.",
                 (("transport", 95), ("practical", 80)), 81),
    PlaceTypeDef("railway_station", "Railway Station", 80, "A railway station.",
                 (("transport", 95), ("practical", 80)), 82),
    PlaceTypeDef("metro_station", "Metro Station", 72, "A metro or subway station.",
                 (("transport", 90), ("practical", 75), ("urban", 65)), 240),
    PlaceTypeDef("taxi_jeep_stand", "Taxi or Jeep Stand", 75, "Where shared jeeps and taxis wait.",
                 (("transport", 85), ("practical", 80))),
    PlaceTypeDef("ferry_terminal", "Ferry Terminal", 70, "A ferry terminal.",
                 (("transport", 85), ("water", 60)), 83),
    PlaceTypeDef("cable_car", "Cable Car", 72, "A cable car or ropeway.",
                 (("transport", 75), ("scenic_spot", 80), ("adventure", 65)), 236),
    PlaceTypeDef("heritage_railway", "Heritage Railway", 68, "A preserved historic railway.",
                 (("transport", 70), ("historical", 75), ("culture_heritage", 65)), 248),
    PlaceTypeDef("road_highway", "Road or Highway", 55, "A named road or highway.",
                 (("transport", 70),), 259),
    PlaceTypeDef("tunnel", "Tunnel", 52, "A tunnel.", (("transport", 70),), 237),

    # --- Recreation, sport & entertainment ----------------------------------
    PlaceTypeDef("ski_resort", "Ski Resort", 72, "A ski resort.",
                 (("sport", 85), ("adventure", 80), ("lodging", 60), ("nature", 60)), 99),
    PlaceTypeDef("diving_spot", "Diving Spot", 72, "A dive site.",
                 (("adventure", 85), ("water", 90), ("wildlife", 60)), 72),
    PlaceTypeDef("golf_course", "Golf Course", 55, "A golf course.", (("sport", 75),), 98),
    PlaceTypeDef("stadium", "Stadium", 62, "A stadium.",
                 (("sport", 85), ("entertainment", 65)), 200),
    PlaceTypeDef("sporting_area", "Sporting Area", 55, "A sports ground.", (("sport", 80),), 41),
    PlaceTypeDef("pool", "Swimming Pool", 52, "A swimming pool.",
                 (("sport", 60), ("water", 60), ("family", 60)), 42),
    PlaceTypeDef("fitness_centre", "Fitness Centre", 48, "A gym.",
                 (("sport", 65), ("health", 55)), 43),
    PlaceTypeDef("amusement_park", "Amusement Park", 70, "An amusement park.",
                 (("entertainment", 90), ("family", 90)), 168),
    PlaceTypeDef("water_park", "Water Park", 65, "A water park.",
                 (("entertainment", 85), ("family", 85), ("water", 75))),
    PlaceTypeDef("theatre", "Theatre", 68, "A theatre.",
                 (("entertainment", 85), ("culture_heritage", 70)), 179),
    PlaceTypeDef("concert_hall", "Concert Hall", 68, "A concert hall.",
                 (("entertainment", 85), ("culture_heritage", 70)), 39),
    PlaceTypeDef("opera_house", "Opera House", 72, "An opera house.",
                 (("entertainment", 85), ("culture_heritage", 80)), 139),
    PlaceTypeDef("cinema", "Cinema", 55, "A cinema.", (("entertainment", 75),), 156),
    PlaceTypeDef("nightclub", "Nightclub", 58, "A nightclub.",
                 (("nightlife", 95), ("entertainment", 70)), 38),
    PlaceTypeDef("casino", "Casino", 55, "A casino.",
                 (("entertainment", 70), ("nightlife", 70)), 86),
    PlaceTypeDef("fairground", "Fairground", 58, "A fairground.",
                 (("entertainment", 70), ("local_life", 65)), 250),

    # --- Education & science ------------------------------------------------
    PlaceTypeDef("observatory", "Observatory", 70, "An astronomical observatory.",
                 (("education", 80), ("scenic_spot", 65)), 211),
    PlaceTypeDef("planetarium", "Planetarium", 62, "A planetarium.",
                 (("education", 80), ("family", 70)), 243),
    PlaceTypeDef("library", "Library", 58, "A library.", (("education", 75),), 212),
    PlaceTypeDef("university", "University", 60, "A university or college.",
                 (("education", 80), ("urban", 55)), 228),
    PlaceTypeDef("school", "School", 48, "A school.", (("education", 70),), 261),
    PlaceTypeDef("research_centre", "Research Centre", 55, "A research institute.",
                 (("education", 75),), 213),

    # --- Urban & civic ------------------------------------------------------
    PlaceTypeDef("skyscraper", "Skyscraper", 65, "A skyscraper.",
                 (("urban", 80), ("scenic_spot", 70)), 138),
    PlaceTypeDef("key_building", "Key Building", 60, "An architecturally notable building.",
                 (("urban", 70), ("culture_heritage", 60)), 26),
    PlaceTypeDef("government_building", "Government Building", 50, "A government building.",
                 (("urban", 60), ("practical", 55)), 171),
    PlaceTypeDef("town_hall", "Town Hall", 52, "A town hall.",
                 (("urban", 60), ("historical", 55)), 251),
    PlaceTypeDef("courthouse", "Courthouse", 45, "A courthouse.", (("urban", 55),), 172),
    PlaceTypeDef("parliament", "Parliament", 58, "A parliament building.",
                 (("urban", 65), ("historical", 60)), 173),
    PlaceTypeDef("convention_centre", "Convention Centre", 45, "A convention centre.",
                 (("urban", 60), ("services", 55)), 152),
    PlaceTypeDef("mine", "Mine", 50, "A mine.",
                 (("historical", 65), ("urban", 45)), 208),
    PlaceTypeDef("power_station", "Power Station", 40, "A power station.",
                 (("urban", 45),), 229),

    # --- Structural ---------------------------------------------------------
    # Mirrors the reverse-geocoded AREA concept. An area is a real place_type
    # (a guide can stand in Thamel), but what is INTERESTING about an area is
    # never implied by its being one -- hence no themes here. Thamel's
    # Shopping/Food/Trekking themes come from curation or the AI classifier,
    # which is exactly the case that fallback exists for.
    PlaceTypeDef("area", "Area", 40,
                 "A named neighbourhood, village, town or district rather than a single venue.",
                 (("area", 100),)),
    PlaceTypeDef("other", "Other", 10, "Nothing specific established about what this place is.",
                 (("other", 100),)),
)


# --- Lookups ----------------------------------------------------------------

THEMES_BY_SLUG: dict[str, ThemeDef] = {theme.slug: theme for theme in THEMES}
PLACE_TYPES_BY_SLUG: dict[str, PlaceTypeDef] = {pt.slug: pt for pt in PLACE_TYPES}

OTHER_PLACE_TYPE = "other"
OTHER_THEME = "other"
AREA_PLACE_TYPE = "area"
AREA_THEME = "area"


# A slug is unique WITHIN a kind, not across both -- the catalog's natural key
# is (kind, slug). Three slugs deliberately exist as both, because they name
# genuinely different things:
#   'trail'  -- theme: "this concerns the walking route itself"
#               place_type: "this place IS a trail"
#   'area'   -- theme: "this is area-level rather than venue-level information"
#               place_type: "this place IS a named area"
#   'other'  -- the honest unknown, in each vocabulary separately
# Renaming either side to force global uniqueness would have made one of them
# read worse than the concept it names, so the composite key is the honest
# shape. Every lookup below therefore takes a kind.
DUAL_KIND_SLUGS = frozenset({"trail", "area", "other"})


def exists(kind: str, slug: str) -> bool:
    """Is (kind, slug) a real catalog entry? The single validity check --
    used by the AI classifier to reject anything it invented."""
    if kind == KIND_THEME:
        return slug in THEMES_BY_SLUG
    if kind == KIND_PLACE_TYPE:
        return slug in PLACE_TYPES_BY_SLUG
    return False


def default_priority_for(kind: str, slug: str) -> int:
    """The catalog's general-importance value, used as the fallback relevance
    when nothing location-specific is known. 0 for an unknown entry."""
    if kind == KIND_THEME:
        theme = THEMES_BY_SLUG.get(slug)
        return theme.default_priority if theme else 0
    if kind == KIND_PLACE_TYPE:
        place_type = PLACE_TYPES_BY_SLUG.get(slug)
        return place_type.default_priority if place_type else 0
    return 0


def display_name_for(kind: str, slug: str) -> str | None:
    if kind == KIND_THEME:
        theme = THEMES_BY_SLUG.get(slug)
        return theme.display_name if theme else None
    if kind == KIND_PLACE_TYPE:
        place_type = PLACE_TYPES_BY_SLUG.get(slug)
        return place_type.display_name if place_type else None
    return None


# --- Bridges to the legacy single-category columns ---------------------------
#
# These exist so the NEW system can agree with the OLD columns rather than
# drift from them. `Location.category`/`subcategory` keep being written
# exactly as before (see the module docstring); these maps let the primary
# assignment be derived from, and checked against, those same values -- and
# let Locations that predate this system be backfilled from what they already
# say about themselves.

LEGACY_CATEGORY_TO_THEME: dict[str, str] = {
    "Trail": "trail",
    "Nature": "nature",
    "Scenic Spot": "scenic_spot",
    "Culture & Heritage": "culture_heritage",
    "Food & Drink": "food_drink",
    "Lodging": "lodging",
    "Shopping": "shopping",
    "Transport": "transport",
    "Health": "health",
    "Finance": "finance",
    "Safety": "safety",
    "Postal": "postal",
    "Nightlife": "nightlife",
    "Services": "services",
    "Area": "area",
    "Other": "other",
}

LEGACY_SUBCATEGORY_TO_PLACE_TYPE: dict[str, str] = {
    "Bridge": "bridge",
    "Trailhead": "trailhead",
    "Campsite": "campsite",
    "Mountain Peak": "mountain_peak",
    "Lake": "lake",
    "River": "river",
    "Beach": "beach",
    "Nature Reserve": "nature_reserve",
    "Viewpoint": "viewpoint",
    "Religious Site": "temple",
    "Museum": "museum",
    "Historical Site": "historical_site",
    "Monument": "monument",
    "Cafe": "cafe",
    "Restaurant": "restaurant",
    "Bakery": "bakery",
    "Market": "market",
    "Tea Stall": "tea_stall",
    "Guesthouse": "guesthouse",
    "Shop": "shop",
    "Gift Shop": "gift_shop",
    "Tour Operator": "tour_operator",
    "Bar": "bar",
    "Pub": "pub",
    "Airport": "airport",
    "Airline Office": "airline_office",
    "Ticketing": "ticketing_office",
    "Hospital": "hospital",
    "Bank": "bank",
    "Police": "police_post",
    "Post Office": "post_office",
    # The four AREA tiers all collapse to the single `area` place_type: the
    # tier lives on in `Location.subcategory`, which is where the area reuse
    # radius is looked up from and which this system never touches.
    "Neighbourhood": "area",
    "Village or Ward": "area",
    "Town or City": "area",
    "District": "area",
    "Other": "other",
}
