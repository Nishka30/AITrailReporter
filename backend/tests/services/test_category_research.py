"""Unit coverage for app/services/category_research.py -- Part 1 of the
knowledge-architecture hardening pass (reuse existing Perplexity research
before ever running a new query; run at most one targeted query when nothing
existing is relevant; never let research directly create knowledge).

Uses a lightweight fake row (not the real ORM model) for the pure scoring
functions (find_relevant_finding logic tested indirectly through the module's
own helpers is unnecessary complexity -- these tests exercise the real
functions against real PlaceResearchFinding-shaped objects via a minimal
in-memory fake session, matching the style of test_category_knowledge.py's
FakeItem approach for functions that only ever read/compare in Python).
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.services import category_research


@dataclass
class FakeFinding:
    id: object
    location_id: object
    topic: str
    summary: str
    source_urls: list | None
    retrieved_at: datetime


def test_row_is_usable_requires_sources_and_length():
    usable = FakeFinding(uuid4(), uuid4(), "interest", "x" * 50, ["https://example.com"], datetime.now(timezone.utc))
    no_sources = FakeFinding(uuid4(), uuid4(), "interest", "x" * 50, None, datetime.now(timezone.utc))
    too_short = FakeFinding(uuid4(), uuid4(), "interest", "short", ["https://example.com"], datetime.now(timezone.utc))

    assert category_research._row_is_usable(usable) is True
    assert category_research._row_is_usable(no_sources) is False
    assert category_research._row_is_usable(too_short) is False


def test_category_keywords_drops_short_words():
    keywords = category_research._category_keywords("food_drink", "Food & Drink")
    assert "food" in keywords
    assert "drink" in keywords
    # "&" strips to nothing meaningful; no 1-2 char tokens survive.
    assert all(len(w) > 2 for w in keywords)


def test_category_topic_is_namespaced_and_distinct_from_plan_topics():
    topic = category_research._category_topic("adventure")
    assert topic == "category:adventure"
    assert topic not in ("interest", "current")


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)


class FakeSessionForFindings:
    """A minimal stand-in for Session.execute(select(PlaceResearchFinding)...)
    that just returns whatever rows were seeded, regardless of the exact
    WHERE clause -- sufficient for testing find_relevant_finding's SCORING
    logic (which happens entirely in Python after the rows come back), not
    the SQL itself (covered by the real-DB integration test instead)."""

    def __init__(self, rows):
        self.rows = rows

    def execute(self, _stmt):
        return _FakeResult(self.rows)


def test_find_relevant_finding_picks_highest_keyword_overlap():
    location_id = uuid4()
    irrelevant = FakeFinding(
        uuid4(), location_id, "interest",
        "This cafe is famous for its architecture and old-world charm and history.",
        ["https://a.example.com"], datetime.now(timezone.utc),
    )
    relevant = FakeFinding(
        uuid4(), location_id, "interest",
        "The cafe sits at the start of a popular hiking trail, an adventure spot for trekkers.",
        ["https://b.example.com"], datetime.now(timezone.utc),
    )
    db = FakeSessionForFindings([irrelevant, relevant])

    found = category_research.find_relevant_finding(db, location_id, "adventure", "Adventure")
    assert found is relevant


def test_find_relevant_finding_returns_none_when_nothing_matches():
    location_id = uuid4()
    irrelevant = FakeFinding(
        uuid4(), location_id, "interest",
        "This cafe is famous for its architecture and old-world charm and history.",
        ["https://a.example.com"], datetime.now(timezone.utc),
    )
    db = FakeSessionForFindings([irrelevant])
    found = category_research.find_relevant_finding(db, location_id, "adventure", "Adventure")
    assert found is None
