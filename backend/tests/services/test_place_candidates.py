"""Tests for the category-diverse ranking in app/services/place_candidates.py.

Two layers:
  - Pure unit tests of `_rank`/`_deduplicate`/`_is_offerable` against plain
    fake rows -- no database, no network, exactly the shape
    `_query_nearby`'s SQLAlchemy Row objects have (plain attributes).
  - `find_place_candidates` tests with `_query_nearby` and the
    `poi_discovery_service` calls monkeypatched to canned data, so the
    end-to-end limit/area/no-extra-query behaviour is covered without a real
    Postgres/PostGIS connection.
"""

from dataclasses import dataclass
from uuid import uuid4

import pytest

from app.core.config import settings
from app.schemas.location import PlaceCandidate as PlaceCandidateSchema
from app.services import place_candidates as pc


@dataclass
class FakeRow:
    """Stand-in for a `_query_nearby` SQLAlchemy Row: same field names,
    plain attribute access, nothing database-specific."""

    id: object
    name: str
    distance_meters: float
    latitude: float = 12.9716
    longitude: float = 77.5946
    category: str | None = None
    subcategory: str | None = None
    place_kind: str | None = None
    external_place_id: str | None = None
    provider: str | None = "google"
    formatted_address: str | None = None
    coordinate_confidence: str | None = None
    coordinate_type: str | None = None


def row(name, distance, category=None, subcategory=None, **kwargs) -> FakeRow:
    return FakeRow(
        id=uuid4(), name=name, distance_meters=distance, category=category, subcategory=subcategory, **kwargs
    )


# ---------------------------------------------------------------------------
# _rank: category-diverse round robin
# ---------------------------------------------------------------------------


def test_dominant_category_does_not_crowd_out_the_others():
    """The exact scenario from the bug report: eight nearby restaurants must
    not push every other nearby category out of the list."""
    rows = [row(f"Restaurant {i}", 50 + i * 10, "Food & Drink", "Restaurant") for i in range(8)]
    rows += [
        row("Green Park", 300, "Nature", "Nature Reserve"),
        row("City Museum", 350, "Culture & Heritage", "Museum"),
        row("Grand Hotel", 400, "Lodging", "Guesthouse"),
        row("Shiva Temple", 450, "Culture & Heritage", "Religious Site"),
    ]

    ranked = pc._rank(rows, limit=9, category_cap=3)
    categories_present = {r.category for r in ranked}

    assert "Nature" in categories_present
    assert "Lodging" in categories_present
    assert "Culture & Heritage" in categories_present
    # Never more than category_cap from the dominant category.
    assert sum(1 for r in ranked if r.category == "Food & Drink") <= 3


def test_single_category_fills_the_list_when_nothing_else_is_nearby():
    rows = [row(f"Restaurant {i}", 50 + i * 10, "Food & Drink", "Restaurant") for i in range(5)]

    ranked = pc._rank(rows, limit=9, category_cap=3)

    # Capped at category_cap even though it's the only category -- a thin
    # list of ONE kind of place is exactly what "only restaurants nearby"
    # should look like, capped the same as any other bucket.
    assert len(ranked) == 3
    assert all(r.category == "Food & Drink" for r in ranked)


def test_many_categories_stay_bounded_by_limit():
    rows = [row(f"Place {i}", 100 + i * 10, category=f"Category {i}") for i in range(15)]

    ranked = pc._rank(rows, limit=9, category_cap=3)

    assert len(ranked) == 9


def test_fewer_candidates_than_limit_are_not_padded():
    rows = [
        row("Only Restaurant", 80, "Food & Drink", "Restaurant"),
        row("Only Park", 200, "Nature", "Nature Reserve"),
    ]

    ranked = pc._rank(rows, limit=9, category_cap=3)

    assert len(ranked) == 2


def test_category_cap_is_respected_and_configurable():
    rows = [row(f"Restaurant {i}", 50 + i * 10, "Food & Drink", "Restaurant") for i in range(10)]

    assert len(pc._rank(rows, limit=9, category_cap=3)) == 3
    assert len(pc._rank(rows, limit=9, category_cap=1)) == 1
    assert len(pc._rank(rows, limit=9, category_cap=5)) == 5


def test_distance_ordering_preserved_within_a_category():
    rows = [
        row("Far Restaurant", 500, "Food & Drink", "Restaurant"),
        row("Near Restaurant", 50, "Food & Drink", "Restaurant"),
        row("Mid Restaurant", 200, "Food & Drink", "Restaurant"),
    ]

    ranked = pc._rank(rows, limit=9, category_cap=3)

    assert [r.name for r in ranked] == ["Near Restaurant", "Mid Restaurant", "Far Restaurant"]


def test_unclassified_candidates_are_offered_in_their_own_bucket():
    rows = [
        row("Mystery Spot", 50, category=None),
        row("Restaurant A", 60, "Food & Drink", "Restaurant"),
    ]

    ranked = pc._rank(rows, limit=9, category_cap=3)

    assert {r.name for r in ranked} == {"Mystery Spot", "Restaurant A"}


def test_low_confidence_and_unclassified_penalties_still_apply_within_bucket():
    rows = [
        row("High Confidence", 100, "Food & Drink", "Restaurant", coordinate_confidence="High"),
        row("Low Confidence Closer", 60, "Food & Drink", "Restaurant", coordinate_confidence="Low"),
    ]

    ranked = pc._rank(rows, limit=9, category_cap=3)

    # 60 + 60 (low-confidence penalty) = 120, still behind the 100m one.
    assert [r.name for r in ranked] == ["High Confidence", "Low Confidence Closer"]


def test_ranking_is_deterministic():
    rows = [row(f"Place {i}", 50 + i * 7, category=f"Category {i % 4}") for i in range(20)]

    first = pc._rank(list(rows), limit=9, category_cap=3)
    second = pc._rank(list(rows), limit=9, category_cap=3)

    assert [r.id for r in first] == [r.id for r in second]


def test_round_robin_visits_categories_by_their_best_candidate_first():
    """Within a round, the category whose next candidate is closest goes
    first -- diversity decides WHICH category is next, not that a closer
    place ever loses to a farther one from a fresher category."""
    rows = [
        row("Park", 500, "Nature", "Nature Reserve"),
        row("Restaurant", 50, "Food & Drink", "Restaurant"),
        row("Temple", 300, "Culture & Heritage", "Religious Site"),
    ]

    ranked = pc._rank(rows, limit=9, category_cap=3)

    assert [r.name for r in ranked] == ["Restaurant", "Temple", "Park"]


# ---------------------------------------------------------------------------
# Unchanged building blocks: dedup and offerability are untouched by this
# change, but re-asserted here so a future edit to _rank can't silently
# break the invariants it depends on.
# ---------------------------------------------------------------------------


def test_deduplicate_still_collapses_same_external_id():
    shared_id = "google-123"
    rows = [
        row("Cafe Coffee Day", 50, "Food & Drink", "Cafe", external_place_id=shared_id, provider="google"),
        row("Cafe Coffee Day", 55, "Food & Drink", "Cafe", external_place_id=shared_id, provider="google"),
    ]

    deduped = pc._deduplicate(rows)

    assert len(deduped) == 1
    assert deduped[0].name == "Cafe Coffee Day"


def test_is_offerable_still_rejects_administrative_names():
    admin_row = row("Madhapur Ward 12", 50, "Other", "Other")
    assert pc._is_offerable(admin_row) is False


# ---------------------------------------------------------------------------
# find_place_candidates: end-to-end with discovery/query monkeypatched
# ---------------------------------------------------------------------------


class _FakeAreaLocation:
    def __init__(self, name="Madhapur"):
        self.id = uuid4()
        self.name = name
        self.latitude = 12.9716
        self.longitude = 77.5946
        self.category = "Area"
        self.subcategory = "Neighbourhood"
        self.place_kind = None
        self.external_place_id = None
        self.provider = "google"
        self.formatted_address = None
        self.coordinate_confidence = None
        self.coordinate_type = None


@pytest.fixture
def no_op_discovery(monkeypatch):
    """Stubs out the two best-effort Google-touching calls `find_place_candidates`
    makes, so no network/DB access happens and call counts are observable."""
    monkeypatch.setattr(pc.poi_discovery_service, "maybe_ensure_discovered", lambda *a, **k: None)
    area_calls = {"count": 0}

    def fake_resolve_area(*a, **k):
        area_calls["count"] += 1
        return None

    monkeypatch.setattr(pc.poi_discovery_service, "maybe_resolve_area_place", fake_resolve_area)
    return area_calls


def _patch_query_nearby(monkeypatch, rows):
    calls = {"count": 0}

    def fake_query_nearby(db, latitude, longitude, radius_meters):
        calls["count"] += 1
        return rows

    monkeypatch.setattr(pc, "_query_nearby", fake_query_nearby)
    return calls


def test_find_place_candidates_default_limit_is_nine(monkeypatch, no_op_discovery):
    rows = [row(f"Place {i}", 50 + i * 10, category=f"Category {i}") for i in range(15)]
    _patch_query_nearby(monkeypatch, rows)

    results = pc.find_place_candidates(db=None, latitude=12.97, longitude=77.59)

    assert settings.place_candidate_limit == 9
    assert len(results) == 9


def test_find_place_candidates_respects_explicit_limit_param(monkeypatch, no_op_discovery):
    rows = [row(f"Place {i}", 50 + i * 10, category=f"Category {i}") for i in range(15)]
    _patch_query_nearby(monkeypatch, rows)

    results = pc.find_place_candidates(db=None, latitude=12.97, longitude=77.59, limit=3)

    assert len(results) == 3


def test_find_place_candidates_makes_exactly_one_nearby_query(monkeypatch, no_op_discovery):
    """No N+1: however many candidates or categories are involved, the
    candidate list must come from a single spatial query."""
    rows = [row(f"Place {i}", 50 + i * 10, category=f"Category {i % 6}") for i in range(30)]
    calls = _patch_query_nearby(monkeypatch, rows)

    pc.find_place_candidates(db=None, latitude=12.97, longitude=77.59)

    assert calls["count"] == 1


def test_find_place_candidates_appends_area_last_and_unaffected_by_diversity(monkeypatch, no_op_discovery):
    # Nine distinct categories so _rank fills the list to the limit on its
    # own (category_cap=3 would otherwise cap a single repeated category
    # well below 9, which is a *different*, already-covered behaviour).
    rows = [row(f"Place {i}", 50 + i * 10, category=f"Category {i}") for i in range(9)]
    _patch_query_nearby(monkeypatch, rows)
    monkeypatch.setattr(
        pc.poi_discovery_service, "maybe_resolve_area_place", lambda *a, **k: _FakeAreaLocation()
    )

    results = pc.find_place_candidates(db=None, latitude=12.97, longitude=77.59)

    assert results[-1].is_area is True
    assert results[-1].name == "Madhapur"
    # The area displaced the least valuable POI rather than being dropped or
    # pushed to exceed the limit.
    assert len(results) == settings.place_candidate_limit
    assert "Place 8" not in {r.name for r in results}  # the farthest POI, displaced


def test_find_place_candidates_falls_back_to_area_when_no_poi_qualifies(monkeypatch, no_op_discovery):
    _patch_query_nearby(monkeypatch, [])
    monkeypatch.setattr(
        pc.poi_discovery_service, "maybe_resolve_area_place", lambda *a, **k: _FakeAreaLocation()
    )

    results = pc.find_place_candidates(db=None, latitude=12.97, longitude=77.59)

    assert len(results) == 1
    assert results[0].is_area is True


def test_find_place_candidates_response_matches_wire_schema(monkeypatch, no_op_discovery):
    rows = [
        row("Restaurant A", 60, "Food & Drink", "Restaurant"),
        row("Green Park", 300, "Nature", "Nature Reserve"),
    ]
    _patch_query_nearby(monkeypatch, rows)

    results = pc.find_place_candidates(db=None, latitude=12.97, longitude=77.59)

    # Same construction the route uses (locations.py::get_place_candidates) --
    # this fails loudly if PlaceCandidateResult's fields ever drift from the
    # response schema's.
    for candidate in results:
        PlaceCandidateSchema(**vars(candidate))
