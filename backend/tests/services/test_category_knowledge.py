"""Unit tests for the PRIMARY knowledge system's pure derivation logic
(services/category_knowledge.py) -- freshness/stale/missing/partially-stale
state, computed from plain CategoryKnowledge-shaped objects. No database:
these functions take/return plain values, exactly like knowledge_state.py's
own boundary-rule tests elsewhere in this codebase.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.services import category_knowledge as ck


@dataclass
class FakeItem:
    """Stand-in for a CategoryKnowledge row: same field names the pure
    functions actually read, nothing database-specific."""

    last_verified_at: datetime | None
    freshness_duration_hours: int
    active: bool = True


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_unverified_item_has_no_stale_at():
    item = FakeItem(last_verified_at=None, freshness_duration_hours=24)
    assert ck.stale_at(item) is None
    assert ck.is_verified(item) is False
    assert ck.is_fresh(item, NOW) is False
    assert ck.is_stale(item, NOW) is False


def test_verified_item_within_window_is_fresh():
    item = FakeItem(last_verified_at=NOW - timedelta(hours=1), freshness_duration_hours=24)
    assert ck.is_fresh(item, NOW) is True
    assert ck.is_stale(item, NOW) is False


def test_verified_item_past_window_is_stale():
    item = FakeItem(last_verified_at=NOW - timedelta(hours=25), freshness_duration_hours=24)
    assert ck.is_fresh(item, NOW) is False
    assert ck.is_stale(item, NOW) is True


def test_stale_at_is_exactly_last_verified_plus_duration():
    verified = NOW - timedelta(hours=1)
    item = FakeItem(last_verified_at=verified, freshness_duration_hours=90 * 24)
    assert ck.stale_at(item) == verified + timedelta(hours=90 * 24)


def test_exactly_at_the_boundary_is_still_fresh():
    item = FakeItem(last_verified_at=NOW - timedelta(hours=24), freshness_duration_hours=24)
    assert ck.is_fresh(item, NOW) is True


def test_category_state_missing_with_zero_items():
    assert ck.compute_category_state([], NOW) == ck.CATEGORY_STATE_MISSING


def test_category_state_missing_when_only_pending_unverified_items_exist():
    """The core anti-gaming rule: an unverified row (a guide answered, but
    moderation hasn't approved it yet) must NOT count as coverage."""
    items = [FakeItem(last_verified_at=None, freshness_duration_hours=24)]
    assert ck.compute_category_state(items, NOW) == ck.CATEGORY_STATE_MISSING


def test_category_state_fresh_when_all_verified_items_are_fresh():
    items = [
        FakeItem(last_verified_at=NOW - timedelta(hours=1), freshness_duration_hours=24),
        FakeItem(last_verified_at=NOW - timedelta(hours=2), freshness_duration_hours=48),
    ]
    assert ck.compute_category_state(items, NOW) == ck.CATEGORY_STATE_FRESH


def test_category_state_stale_when_all_verified_items_are_stale():
    items = [
        FakeItem(last_verified_at=NOW - timedelta(hours=100), freshness_duration_hours=24),
    ]
    assert ck.compute_category_state(items, NOW) == ck.CATEGORY_STATE_STALE


def test_category_state_partially_stale_with_a_mix():
    items = [
        FakeItem(last_verified_at=NOW - timedelta(hours=1), freshness_duration_hours=24),  # fresh
        FakeItem(last_verified_at=NOW - timedelta(hours=100), freshness_duration_hours=24),  # stale
    ]
    assert ck.compute_category_state(items, NOW) == ck.CATEGORY_STATE_PARTIALLY_STALE


def test_inactive_items_are_excluded_from_state():
    """A superseded (active=False) item must never count toward coverage --
    its replacement is the one that should."""
    items = [FakeItem(last_verified_at=NOW - timedelta(hours=1), freshness_duration_hours=24, active=False)]
    assert ck.compute_category_state(items, NOW) == ck.CATEGORY_STATE_MISSING


def test_category_state_stale_with_all_stale_multiple_items():
    items = [
        FakeItem(last_verified_at=NOW - timedelta(hours=100), freshness_duration_hours=24),
        FakeItem(last_verified_at=NOW - timedelta(hours=200), freshness_duration_hours=48),
    ]
    assert ck.compute_category_state(items, NOW) == ck.CATEGORY_STATE_STALE
