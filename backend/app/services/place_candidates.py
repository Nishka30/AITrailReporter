"""Shortlist of places a guide could choose to contribute to.

WHY A SHORTLIST RATHER THAN ONE ANSWER:
`guides._resolve_position_place` answers "where is this guide?" with exactly
one place, which is right for labelling a position but wrong for deciding what
a contribution is ABOUT. Standing outside a hotel that happens to be the
nearest listed POI does not make the hotel the subject -- the shop next door,
the metro entrance across the road and the mall behind it are equally
plausible, and only the guide knows which one they mean. So GPS narrows the
field and the guide picks; it never picks for them.

WHAT THIS MODULE DOES NOT DO:
It creates nothing and owns no place model. Every candidate is an existing
`Location` row, found through the same discovery path everything else uses
(`poi_discovery.maybe_ensure_discovered`), so two guides who pick the same
place necessarily contribute to the same record. This module only decides
which of those rows to OFFER, and in what order.
"""

import logging
import re
from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.geo import make_point
from app.db.models.location import Location
from app.services import poi_discovery as poi_discovery_service
from app.services.places import categories

logger = logging.getLogger(__name__)

# Treated as "we could not say what this is". A place classified as nothing in
# particular is still offered -- it is a real place someone may want to report
# on -- just ranked below places we can actually describe to the guide.
_UNCLASSIFIED = {None, "", categories.DEFAULT_CATEGORY[0]}


# How much worse an unclassified place is treated, expressed in METRES so it
# composes directly with real distance instead of needing a separate weight
# scale. A classified place 150m away and an unclassified one right here rank
# equally -- enough to break ties, never enough to hide something obviously
# closer.
_UNCLASSIFIED_PENALTY_METERS = 150.0

# Added when a seed-imported candidate's own supplier flagged its coordinate
# as "Low" confidence -- see services/seed_import.py and
# Location.coordinate_confidence's own comment. Smaller than the
# unclassified penalty: an unclassified place tells us nothing about what it
# IS, while a Low-confidence one tells us exactly what it is and roughly
# where -- the uncertainty is narrower, so the penalty is too. This is the
# "do not treat low-confidence coordinates as equally authoritative" rule,
# made concrete: a Low-confidence place a little closer than a High-
# confidence one can still win, but not by treating the two as equal.
_LOW_CONFIDENCE_PENALTY_METERS = 60.0

# Names that describe an administrative unit rather than somewhere a guide can
# stand and report on. Same defensive filter the geocoder applies when naming
# areas -- repeated here because a Location may predate that filter.
_ADMINISTRATIVE_RE = re.compile(
    r"(?i)\b(ward|corporation|municipal(ity)?|panchayat|taluk|tehsil|subdistrict"
    r"|sub-district|zone|constituency|division)\b"
)

# Mean Earth radius. Only ever used to decide whether two candidates are the
# same place, where tens of metres is the resolution that matters -- a sphere
# is ample, and PostGIS already did the authoritative guide-to-place distance.
_EARTH_RADIUS_METERS = 6_371_000.0

# Below this, two tokens occupying the same position in otherwise identical
# names are treated as a deliberate discriminator rather than a misspelling.
# "a"/"b" and "north"/"south" fall below it; "shree"/"shri" does not.
_DISCRIMINATOR_SIMILARITY = 0.4


@dataclass(frozen=True)
class PlaceCandidateResult:
    """One offerable place. Mirrors schemas.location.PlaceCandidate, kept as a
    plain dataclass so the service stays usable outside a request."""

    id: object
    name: str
    distance_meters: float
    latitude: float
    longitude: float
    category: str | None
    subcategory: str | None
    place_kind: str | None
    external_place_id: str | None
    provider: str | None
    formatted_address: str | None
    coordinate_confidence: str | None
    coordinate_type: str | None
    is_area: bool


def _normalized_name(name: str) -> str:
    """Lowercased, punctuation-free, whitespace-collapsed -- for the cheap
    exact-duplicate check before the fuzzy one."""
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def _similarity(a: str, b: str) -> float:
    """Dice coefficient over character bigrams -- the same idea pg_trgm's `%`
    operator implements, computed in Python here because these candidates are
    already loaded and this avoids N extra round trips inside a request.

    Only ever used to HIDE a duplicate from a picker, never to merge rows, so
    an approximate agreement with pg_trgm is fine (see
    place_candidate_name_similarity's comment in config.py).
    """
    if a == b:
        return 1.0
    if len(a) < 2 or len(b) < 2:
        return 0.0
    grams_a = {a[i : i + 2] for i in range(len(a) - 1)}
    grams_b = {b[i : i + 2] for i in range(len(b) - 1)}
    overlap = len(grams_a & grams_b)
    return (2.0 * overlap) / (len(grams_a) + len(grams_b))


def _deliberately_distinguished(a: str, b: str) -> bool:
    """Whether two similar names are two places someone took care to tell
    apart, rather than two spellings of one place.

    Pure name similarity cannot answer this: "Tea Stall A" and "Tea Stall B"
    differ by a single character and are two different stalls, while "Shree
    Shyam Mandir" and "Shri Shyam Mandir" differ by two and are one temple.
    What separates them is WHERE the difference falls and what it looks like:
    a same-length name differing in exactly one token, where that token is
    itself nothing like its counterpart, is a deliberate discriminator --
    A/B, 1/2, North/South.

    Returning True means "keep both", so the failure mode is a duplicate in
    the picker rather than a real place the guide cannot choose. That is the
    right way round: they can ignore a duplicate, but they cannot select
    something we never offered.
    """
    tokens_a, tokens_b = a.split(), b.split()
    if len(tokens_a) != len(tokens_b):
        # An inserted or dropped word ("Forum Mall" vs "Forum Sujana Mall") is
        # how the SAME place gets recorded twice, not how two are told apart.
        return False
    differing = [(x, y) for x, y in zip(tokens_a, tokens_b) if x != y]
    if len(differing) != 1:
        return False
    left, right = differing[0]
    return _similarity(left, right) < _DISCRIMINATOR_SIMILARITY


def _is_offerable(row) -> bool:
    """Whether this row is a place a guide could meaningfully report on."""
    name = (row.name or "").strip()
    if not name:
        return False
    # An administrative unit is a label on a map, not somewhere to stand.
    # Areas are exempt: "Madhapur" is a legitimate broadest-option candidate
    # even though its name is administrative in origin.
    if row.category != categories.AREA_CATEGORY and _ADMINISTRATIVE_RE.search(name):
        return False
    return True


def _metres_apart(a, b) -> float:
    """Great-circle distance between two candidate rows.

    Computed from the rows' own coordinates rather than by comparing their
    distances from the guide: two places can both be 100m away in opposite
    directions and so be 200m apart, which a difference-of-distances check
    would read as "0m apart" and wrongly merge.
    """
    lat_a, lon_a = radians(float(a.latitude)), radians(float(a.longitude))
    lat_b, lon_b = radians(float(b.latitude)), radians(float(b.longitude))
    d_lat, d_lon = lat_b - lat_a, lon_b - lon_a
    h = sin(d_lat / 2) ** 2 + cos(lat_a) * cos(lat_b) * sin(d_lon / 2) ** 2
    return 2 * _EARTH_RADIUS_METERS * asin(min(1.0, sqrt(h)))


def _deduplicate(rows: list) -> list:
    """Collapses rows that represent the same real-world place.

    Two gates:
      1. Same (provider, external_place_id) -- Google saying "this is the same
         place", which is conclusive at any distance.
      2. Similar name AND physically close -- "Forum Mall" vs "Forum Sujana
         Mall" 40m apart.

    Gate 2 is deliberately BOTH conditions, never name alone. Two branches of
    one chain ("Cafe Coffee Day" at either end of a road) share a name exactly
    but are different places a guide might report on, and collapsing them
    would silently remove the one they are standing at. Proximity is what
    separates "indexed twice" from "there are two of them".

    Rows arrive nearest-first, so the survivor of any collision is always the
    closest representation of that place -- the one whose distance the guide
    can verify by looking up.

    This never deletes or merges anything in the database. Two rows that ARE
    genuinely duplicates in storage stay that way; they are simply not both
    offered. Repairing storage-level duplicates is a separate, destructive
    concern and deliberately not done from a read path.
    """
    kept: list = []
    seen_external: set[tuple[str, str]] = set()

    for row in rows:
        if row.provider and row.external_place_id:
            identity = (row.provider, row.external_place_id)
            if identity in seen_external:
                continue
            seen_external.add(identity)

        normalized = _normalized_name(row.name)
        duplicate = False
        for existing in kept:
            if _metres_apart(row, existing) > settings.place_candidate_dedup_radius_meters:
                continue
            existing_name = _normalized_name(existing.name)
            if _deliberately_distinguished(normalized, existing_name):
                continue
            if _similarity(normalized, existing_name) >= settings.place_candidate_name_similarity:
                duplicate = True
                break
        if duplicate:
            continue

        kept.append(row)

    return kept


def _base_score(row) -> float:
    """Distance, adjusted for how useful the place is to a contributor.

    Everything is in metres so the two concerns compose without an arbitrary
    weighting constant: the adjustment is literally "treat this as if it were
    N metres further away".
    """
    score = float(row.distance_meters)
    if row.category in _UNCLASSIFIED:
        score += _UNCLASSIFIED_PENALTY_METERS
    if row.coordinate_confidence == "Low":
        score += _LOW_CONFIDENCE_PENALTY_METERS
    return score


def _rank(rows: list, limit: int, category_cap: int) -> list:
    """Category-diverse selection: bucket by TrailMind category, rank each
    bucket by distance/quality, then round-robin across buckets so one dense
    category cannot fill the whole list on its own.

    Why buckets-and-rounds rather than one sort with a penalty (the previous
    approach): a flat per-repeat penalty is either too weak to matter (an
    8th restaurant still beats a 1st park a little further out, exactly the
    dominance this replaces) or, made strong enough to fix that, starts
    dropping obviously closer places for no good reason. Guaranteeing each
    present category an actual turn is what the task calls for, not a bigger
    distance fudge.

    Each round orders the categories that still have something to offer by
    THEIR OWN best remaining candidate's score, and takes one from each in
    that order -- so distance still decides who goes first within a round,
    and diversity only decides which category's turn is next, never
    overrides a closer place with a worse one just to vary the category. A
    category drops out once it has contributed `category_cap` candidates (a
    soft ceiling, never a reason to pad a thin list) or has none left.
    Selection stops once `limit` is reached or every category has dropped
    out -- so a single real category still fills the list on its own when
    nothing else is around, exactly as it did before.

    Rows within a bucket are pre-sorted by _base_score, the same
    distance-plus-confidence adjustment ranking has always used, so ordering
    inside a category is unchanged from before this function existed.
    """
    buckets: dict[str, list] = {}
    for row in rows:
        buckets.setdefault(row.category or "?", []).append(row)
    for bucket in buckets.values():
        bucket.sort(key=_base_score)

    taken: dict[str, int] = dict.fromkeys(buckets, 0)
    chosen: list = []

    while len(chosen) < limit:
        available = [
            key
            for key, bucket in buckets.items()
            if taken[key] < category_cap and taken[key] < len(bucket)
        ]
        if not available:
            break
        available.sort(key=lambda key: _base_score(buckets[key][taken[key]]))
        for key in available:
            if len(chosen) >= limit:
                break
            chosen.append(buckets[key][taken[key]])
            taken[key] += 1

    return chosen


def _to_result(row, *, is_area: bool) -> PlaceCandidateResult:
    return PlaceCandidateResult(
        id=row.id,
        name=row.name,
        # An AREA is a region the coordinate falls INSIDE, so the honest gap is
        # zero -- the stored row's coordinates are the area's centroid, which
        # is a different thing and would be misleading to report as distance.
        # Same rule guides._resolve_position_place already applies.
        distance_meters=0.0 if is_area else float(row.distance_meters),
        latitude=float(row.latitude),
        longitude=float(row.longitude),
        category=row.category,
        subcategory=row.subcategory,
        place_kind=row.place_kind,
        external_place_id=row.external_place_id,
        provider=row.provider,
        formatted_address=row.formatted_address,
        coordinate_confidence=row.coordinate_confidence,
        coordinate_type=row.coordinate_type,
        is_area=is_area,
    )


def _query_nearby(db: Session, latitude: float, longitude: float, radius_meters: float) -> list:
    target = make_point(latitude, longitude)
    distance = func.ST_Distance(Location.geog, target).label("distance_meters")
    stmt = (
        select(
            Location.id,
            Location.name,
            Location.latitude,
            Location.longitude,
            Location.category,
            Location.subcategory,
            Location.place_kind,
            Location.external_place_id,
            Location.provider,
            Location.formatted_address,
            Location.coordinate_confidence,
            Location.coordinate_type,
            distance,
        )
        .where(func.ST_DWithin(Location.geog, target, radius_meters))
        .order_by(distance)
    )
    return list(db.execute(stmt).all())


def find_place_candidates(
    db: Session,
    latitude: float,
    longitude: float,
    *,
    limit: int | None = None,
    radius_meters: float | None = None,
    category_cap: int | None = None,
) -> list[PlaceCandidateResult]:
    """Ranked places the guide could contribute to, nearest and most useful
    first, with the containing area offered last as the broadest option.

    Order of operations, and why:

    1. Discover inline (best-effort, bounded, cost-gated). Without this a
       genuinely new area would offer an empty list on the first visit and
       only fill in later, which reads as "there is nothing here" rather than
       "we haven't looked yet". `maybe_ensure_discovered` already skips the
       Google call entirely when a known place covers this coordinate, so the
       common case costs one PostGIS query.
    2. Read the shared `locations` table. Discovery in step 1 wrote into the
       same table, so there is no separate "found now" vs "known before" path.
    3. Filter, deduplicate, rank.
    4. Append the containing AREA last, and fall back to it entirely when no
       POI qualified -- preserving exactly the behaviour
       `_resolve_position_place` has today for places with no nearby POI.

    Never raises on an external failure: a Google outage degrades this to
    "whatever we already knew about here", which is still a usable list.
    """
    limit = limit or settings.place_candidate_limit
    radius_meters = radius_meters or settings.place_candidate_radius_meters
    category_cap = category_cap or settings.place_candidate_category_cap

    poi_discovery_service.maybe_ensure_discovered(
        db, latitude, longitude, timeout=settings.google_places_inline_timeout_seconds
    )

    rows = _query_nearby(db, latitude, longitude, radius_meters)
    offerable = [row for row in rows if _is_offerable(row)]

    pois = [row for row in offerable if row.category != categories.AREA_CATEGORY]
    # An area's stored coordinates are its centroid, which for anything larger
    # than a small neighbourhood sits outside the candidate radius -- so the
    # areas that happen to fall inside it are not a reliable way to find the
    # one the guide is actually inside. That question has its own resolver.
    ranked = _rank(_deduplicate(pois), limit, category_cap)
    results = [_to_result(row, is_area=False) for row in ranked]

    # The broadest honest option: the named area this coordinate is inside.
    # Offered LAST rather than by distance -- it would otherwise sort first
    # (distance 0) and push every specific place down, which inverts what the
    # guide is being asked. Someone reporting on "Madhapur" in general is a
    # real case, just never the most likely one.
    area = poi_discovery_service.maybe_resolve_area_place(
        db, latitude, longitude, timeout=settings.google_places_inline_timeout_seconds
    )
    if area is not None and not any(result.id == area.id for result in results):
        area_result = PlaceCandidateResult(
            id=area.id,
            name=area.name,
            distance_meters=0.0,
            latitude=float(area.latitude),
            longitude=float(area.longitude),
            category=area.category,
            subcategory=area.subcategory,
            place_kind=area.place_kind,
            external_place_id=area.external_place_id,
            provider=area.provider,
            formatted_address=area.formatted_address,
            coordinate_confidence=area.coordinate_confidence,
            coordinate_type=area.coordinate_type,
            is_area=True,
        )
        if len(results) >= limit:
            # Keep the area reachable even at a full list: the alternative is
            # a guide at a POI-dense spot having no way to report on the area
            # itself. Displacing the furthest POI costs the least.
            results = results[: limit - 1]
        results.append(area_result)

    return results
