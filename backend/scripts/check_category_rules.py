"""Pure-function checks for the Location category classifier.

    python scripts/check_category_rules.py     # exits non-zero on failure

No database, no network, no test framework -- this runs anywhere the backend
package imports. It covers the parts that most deserve a fast check:

  * the catalog's internal consistency (every implied theme exists, no
    duplicate slugs, and every legacy category string still maps to a theme
    whose display name is byte-identical -- which is what keeps the new
    system in agreement with the untouched `locations.category` column);
  * the deterministic rules, including that a name rule refines only the
    place types it is allowed to (a HOSPITAL with "Cafe" in its name must not
    be demoted to a cafe);
  * `is_weak`, which decides whether a place costs a model call at all;
  * the model-output validator, which is the boundary that stops an invented
    category ever reaching the database.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.services.places import categories as legacy_categories
from app.services.places import category_ai as ai
from app.services.places import category_catalog as cc
from app.services.places import category_rules as cr

failures = []


def check(label, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"  {status}  {label}{('  -- ' + detail) if detail else ''}")
    if not cond:
        failures.append(label)


def themes_of(props):
    return {p.slug: p.relevance for p in props if p.kind == "theme"}


def place_type_of(props):
    return next((p.slug for p in props if p.kind == "place_type"), None)


print("1. Catalog integrity")
theme_slugs = {t.slug for t in cc.THEMES}
pt_slugs = {p.slug for p in cc.PLACE_TYPES}
check("no duplicate theme slugs", len(theme_slugs) == len(cc.THEMES))
check("no duplicate place_type slugs", len(pt_slugs) == len(cc.PLACE_TYPES))
check(
    "dual-kind slugs are exactly the declared set",
    (theme_slugs & pt_slugs) == cc.DUAL_KIND_SLUGS,
    str(sorted(theme_slugs & pt_slugs)),
)
check(
    "every implied theme exists",
    all(s in theme_slugs for p in cc.PLACE_TYPES for s, _ in p.themes),
)
check(
    "every implied relevance in range",
    all(0 <= r <= 100 for p in cc.PLACE_TYPES for _, r in p.themes),
)
check(
    "every default_priority in range",
    all(0 <= d.default_priority <= 100 for d in list(cc.THEMES) + list(cc.PLACE_TYPES)),
)
check(
    "every entry has a non-empty description",
    all(d.description.strip() for d in list(cc.THEMES) + list(cc.PLACE_TYPES)),
)
check(
    "legacy category map fully resolves",
    all(cc.exists("theme", v) for v in cc.LEGACY_CATEGORY_TO_THEME.values()),
)
check(
    "legacy subcategory map fully resolves",
    all(cc.exists("place_type", v) for v in cc.LEGACY_SUBCATEGORY_TO_PLACE_TYPE.values()),
)
check(
    "every legacy category string has a byte-identical display_name",
    all(
        cc.display_name_for("theme", slug) == legacy
        for legacy, slug in cc.LEGACY_CATEGORY_TO_THEME.items()
    ),
    "the primary theme must read the same as the legacy column",
)
check(
    "every GOOGLE_TYPE_TO_PLACE_TYPE target exists",
    all(cc.exists("place_type", v) for v in cr.GOOGLE_TYPE_TO_PLACE_TYPE.values()),
)
check(
    "every SEED_TYPE_TO_PLACE_TYPE target exists",
    all(cc.exists("place_type", v) for v in cr.SEED_TYPE_TO_PLACE_TYPE.values()),
)
check(
    "every NAME_RULE target exists",
    all(cc.exists("place_type", r.place_type) for r in cr.NAME_RULES),
)
check(
    "seed type keys match categories.SEED_TYPE_MAP exactly",
    set(cr.SEED_TYPE_TO_PLACE_TYPE) == set(legacy_categories.SEED_TYPE_MAP),
    "the two curated-type vocabularies must not drift apart",
)

print("\n2. Deterministic classification reproduces the worked examples")
temple = cr.classify_categories(primary_type="hindu_temple", name="Pashupatinath Temple")
check("temple -> place_type temple", place_type_of(temple) == "temple")
check(
    "temple -> religious + culture + historical",
    {"religious", "culture_heritage", "historical"} <= set(themes_of(temple)),
)

market = cr.classify_categories(primary_type="market", name="Asan Bazaar")
check(
    "market -> shopping + local_life + food",
    {"shopping", "local_life", "food_drink"} <= set(themes_of(market)),
)

park = cr.classify_categories(primary_type="national_park", name="Sagarmatha National Park")
check(
    "national park -> nature + wildlife + adventure",
    {"nature", "wildlife", "adventure"} <= set(themes_of(park)),
)

print("\n3. Name rules refine only where allowed")
gear = cr.classify_categories(seed_type="Shop", name="Shona's Trekking Gear")
check("shop + 'trekking gear' -> gear_shop", place_type_of(gear) == "gear_shop")
hospital = cr.classify_categories(primary_type="hospital", name="Everest Cafe Hospital")
check(
    "hospital with 'cafe' in its name is NOT demoted to a cafe",
    place_type_of(hospital) == "hospital",
    f"got {place_type_of(hospital)}",
)
tea = cr.classify_categories(primary_type="cafe", name="Himalayan Tea Corner")
check("cafe + 'tea' -> tea_stall (the pre-existing rule, preserved)",
      place_type_of(tea) == "tea_stall")
plain = cr.classify_categories(primary_type="cafe", name="Fire And Ice Pizzeria")
check("a plain cafe stays a cafe", place_type_of(plain) == "cafe")

print("\n4. is_weak triggers exactly where intended")
check("an unknown place is weak", cr.is_weak(cr.classify_categories(name="Mystery Spot")))
check(
    "an area is weak",
    cr.is_weak(cr.classify_categories(primary_type="sublocality_level_1", name="Thamel")),
)
check(
    "a plain restaurant is NOT weak (one real theme is enough)",
    not cr.is_weak(cr.classify_categories(primary_type="restaurant", name="Gaia")),
)
check("a temple is not weak", not cr.is_weak(temple))
ai_described_area = ai.validate_model_output(
    {
        "place_type": "area",
        "themes": [
            {"slug": "shopping", "strength": "defining", "reason": "bazaars"},
            {"slug": "food_drink", "strength": "strong", "reason": "restaurants"},
        ],
    }
)
check(
    "an area the MODEL has already described is no longer weak",
    not cr.is_weak(ai_described_area),
    "otherwise every sweep would re-pay for the same answer forever",
)

print("\n5. Model-output validation rejects anything invented")
out = ai.validate_model_output(
    {
        "place_type": "not_a_real_type",
        "themes": [
            {"slug": "wildlife", "strength": "defining", "reason": "tigers"},
            {"slug": "totally_made_up", "strength": "defining", "reason": "nope"},
            {"slug": "nature", "strength": "not_a_strength", "reason": "bad strength"},
            {"slug": "wildlife", "strength": "related", "reason": "duplicate"},
            {"slug": "other", "strength": "defining", "reason": "uninformative"},
        ],
    }
)
slugs = [p.slug for p in out if p.kind == "theme"]
check("an invented place_type falls back to 'other'", place_type_of(out) == "other")
check("an invented theme is dropped", "totally_made_up" not in slugs)
check("an unknown strength is dropped", "nature" not in slugs)
check("a duplicate theme is collapsed", slugs.count("wildlife") == 1)
check("the uninformative 'other' theme is not assigned", "other" not in slugs)
check("a valid theme survives", "wildlife" in slugs)
check("every source is 'ai'", all(p.source == "ai" for p in out))

many = ai.validate_model_output(
    {
        "place_type": "museum",
        "themes": [
            {"slug": t.slug, "strength": "defining", "reason": "x"}
            for t in cc.THEMES
            if t.slug != "other"
        ],
    }
)
check(
    f"theme count is hard-capped at {ai.MAX_AI_THEMES}",
    len([p for p in many if p.kind == "theme"]) == ai.MAX_AI_THEMES,
    str(len([p for p in many if p.kind == "theme"])),
)

print("\n6. Structural invariants of every proposal set")
for label, props in [
    ("temple", temple),
    ("market", market),
    ("gear", gear),
    ("ai", out),
]:
    check(
        f"{label}: exactly one place_type",
        len([p for p in props if p.kind == "place_type"]) == 1,
    )
    check(
        f"{label}: at most one primary per kind",
        all(
            len([p for p in props if p.kind == k and p.is_primary]) <= 1
            for k in ("theme", "place_type")
        ),
    )
    check(
        f"{label}: every slug is in the catalog",
        all(cc.exists(p.kind, p.slug) for p in props),
    )
    check(
        f"{label}: every source is a known source",
        all(p.source in cr.ASSIGNMENT_SOURCES for p in props),
    )

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("All category rule checks passed.")
