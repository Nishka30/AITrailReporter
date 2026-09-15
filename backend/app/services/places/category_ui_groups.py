"""Presentation-only grouping of the category catalog (category_catalog.py)
into a small set of user-friendly sections for the admin Places filter UI.

WHY THIS EXISTS: category_catalog.py has ~145 place_types and 29 themes --
exactly right for deterministic classification, wildly too many to hand an
admin as a flat filter list. But the groupings an admin actually wants
("Food & Drink", "Culture & Heritage", "Outdoor & Recreation", ...) are
already latent in the catalog's THEMES -- they are, in fact, almost exactly
the themes themselves. This module maps each place_type to ONE UI group by
looking at its highest-relevance implied theme (declared in category_catalog,
never re-decided here), then folds the 29 themes down into a slightly smaller
set of sections so the sidebar doesn't have 29 top-level headings for a
handful of place_types each.

THIS FILE CHANGES NOTHING ABOUT CLASSIFICATION, PRIORITIES OR ASSIGNMENTS. It
is a pure read-side lookup over category_catalog.py's existing data, used only
by admin_places.py to build a filter UI. Renaming or re-priority-ing a
category still happens in category_catalog.py exactly as before; this file
never needs to change when that one does, unless a genuinely NEW theme is
added that isn't covered by THEME_TO_UI_GROUP below (falls back to "other").
"""

from .category_catalog import PLACE_TYPES, PLACE_TYPES_BY_SLUG

# (group_key, display_label), in the order they should appear in the UI.
# "other" is always rendered last regardless of this order (see
# admin_places.py::list_category_filter_options).
UI_GROUPS: tuple[tuple[str, str], ...] = (
    ("nature_scenery", "Nature & Scenery"),
    ("culture_heritage", "Culture & Heritage"),
    ("trail_trekking", "Trail & Trekking"),
    ("food_drink", "Food & Drink"),
    ("lodging", "Lodging & Stays"),
    ("shopping", "Shopping"),
    ("tourism_recreation", "Tourism & Recreation"),
    ("transport", "Transport"),
    ("practical_services", "Practical & Services"),
    ("other", "Other"),
)

# Every theme slug in category_catalog.THEMES must appear here (falls back to
# "other" if a new theme is ever added without updating this map).
THEME_TO_UI_GROUP: dict[str, str] = {
    "nature": "nature_scenery",
    "wildlife": "nature_scenery",
    "water": "nature_scenery",
    "scenic_spot": "nature_scenery",
    "photography": "nature_scenery",
    "adventure": "nature_scenery",
    "culture_heritage": "culture_heritage",
    "historical": "culture_heritage",
    "religious": "culture_heritage",
    "local_life": "culture_heritage",
    "trail": "trail_trekking",
    "trekking": "trail_trekking",
    "food_drink": "food_drink",
    "nightlife": "food_drink",
    "lodging": "lodging",
    "shopping": "shopping",
    "entertainment": "tourism_recreation",
    "sport": "tourism_recreation",
    "family": "tourism_recreation",
    "education": "tourism_recreation",
    "transport": "transport",
    "practical": "practical_services",
    "health": "practical_services",
    "safety": "practical_services",
    "finance": "practical_services",
    "postal": "practical_services",
    "services": "practical_services",
    "urban": "practical_services",
    "area": "other",
    "other": "other",
}

UI_GROUP_LABELS: dict[str, str] = dict(UI_GROUPS)


def group_label(group_key: str) -> str:
    return UI_GROUP_LABELS.get(group_key, "Other")


def place_type_ui_group(slug: str) -> str:
    """Which UI group a place_type belongs in, derived from the HIGHEST-
    relevance theme it implies (the theme that best answers "what is this
    place mainly about") -- never decided independently of the catalog.
    Unknown slug or one with no declared themes -> "other"."""
    place_type = PLACE_TYPES_BY_SLUG.get(slug)
    if place_type is None or not place_type.themes:
        return "other"
    best_theme_slug = max(place_type.themes, key=lambda pair: pair[1])[0]
    return THEME_TO_UI_GROUP.get(best_theme_slug, "other")


def all_place_type_slugs_in_group(group_key: str) -> list[str]:
    """Every place_type slug whose UI group is this one -- used to resolve a
    "browse this whole group" filter down to the concrete slugs to query."""
    return [pt.slug for pt in PLACE_TYPES if place_type_ui_group(pt.slug) == group_key]


__all__ = [
    "UI_GROUPS",
    "group_label",
    "place_type_ui_group",
    "all_place_type_slugs_in_group",
]
