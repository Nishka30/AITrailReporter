"""Coverage for the reusable, structured Location research summary (for the
future Travelers website) -- see app/db/models/location_research_summary.py
and app/services/place_summary_service.py.

Runs against the real dev Postgres database, same convention as
test_category_research_flow.py: no mocking of the DB or of
ensure_researched's own locking/generation logic. Only the two external
providers (Perplexity, the place-question Anthropic call, and the
place-summary Anthropic call) are monkeypatched.

Covers:
  A. A successful run produces a structured, citation-checked summary.
  B. A regeneration overwrites the previous summary in place (no duplicate row).
  C. A summary citing no genuinely-retrieved URL is dropped (stored as empty,
     not fabricated), mirroring place_question_research/validation.py's rule.
  D. A summary-generation failure never affects question generation, and vice
     versa -- the two are independent best-effort steps.
  E. Summary generation never creates/mutates CategoryKnowledge -- same trust
     boundary already enforced for category-driven question research.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.db.geo import make_point
from app.db.models.category_knowledge import CategoryKnowledge
from app.db.models.location import Location
from app.db.session import SessionLocal
from app.services import place_questions as place_question_service
from app.services import place_summary_service
from app.services.place_summary.anthropic_provider import PlaceSummaryProviderError
from app.services.research.base import ResearchFinding, ResearchSource


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def location(db):
    loc = Location(
        name=f"Test Summary Location {uuid4().hex[:8]}",
        latitude=27.7172,
        longitude=85.3240,
        geog=make_point(27.7172, 85.3240),
        source="manual",
        locality="Test Locality",  # set so _resolve_locality never calls Google.
    )
    db.add(loc)
    db.commit()
    db.refresh(loc)
    yield loc
    db.execute(text("delete from location_research_summaries where location_id = :id"), {"id": str(loc.id)})
    db.execute(text("delete from place_research_findings where location_id = :id"), {"id": str(loc.id)})
    db.execute(text("delete from place_questions where location_id = :id"), {"id": str(loc.id)})
    db.execute(text("delete from place_question_research where location_id = :id"), {"id": str(loc.id)})
    db.execute(text("delete from locations where id = :id"), {"id": str(loc.id)})
    db.commit()


class _FakeProvider:
    """Mirrors test_category_research_flow.py's fake provider -- returns one
    usable finding for the 'interest' query, nothing for 'current'."""

    def run_query(self, query, *, topic, recency=None):
        return ResearchFinding(
            topic=topic,
            query=query,
            summary="Visitors specifically mention the carved wooden doors and a small "
            "shrine at the back that is easy to miss, according to several travel blogs.",
            provider="perplexity",
            model="sonar",
            retrieved_at=datetime.now(timezone.utc),
            sources=[ResearchSource(url="https://example.com/review", title="A travel blog")],
        )


def _no_questions_stub(*args, **kwargs):
    return {"questions": [], "found_information": False}


def _run(db, location, monkeypatch, summary_stub):
    monkeypatch.setattr(
        "app.services.place_questions.perplexity_provider.get_provider",
        lambda: _FakeProvider(),
    )
    monkeypatch.setattr(
        "app.services.place_questions.anthropic_provider.generate_place_questions",
        _no_questions_stub,
    )
    monkeypatch.setattr(
        "app.services.place_summary_service.anthropic_provider.generate_place_summary",
        summary_stub,
    )
    return place_question_service.ensure_researched(db, location.id, force=True)


def test_a_successful_run_produces_a_structured_summary(db, location, monkeypatch):
    def _summary_stub(*args, **kwargs):
        return {
            "found_information": True,
            "description": "A small temple known for its carved wooden doors.",
            "known_for": "Its carved wooden doors and a hidden back shrine.",
            "highlights": ["Carved wooden doors", "A small shrine at the back"],
            "things_to_do": ["Look for the back shrine"],
            "important_facts": [],
            "practical_info": None,
            "warnings": [],
            "source_urls": ["https://example.com/review"],
        }

    _run(db, location, monkeypatch, _summary_stub)

    summary = place_summary_service.get_summary(db, location.id)
    assert summary is not None
    assert summary.status == "completed"
    assert summary.description == "A small temple known for its carved wooden doors."
    assert summary.highlights == ["Carved wooden doors", "A small shrine at the back"]
    assert summary.source_urls == ["https://example.com/review"]
    assert summary.researched_at is not None

    read = place_summary_service.to_read(summary)
    assert read.status == "completed"
    assert read.known_for == "Its carved wooden doors and a hidden back shrine."


def test_b_regeneration_overwrites_in_place_no_duplicate_row(db, location, monkeypatch):
    def _first(*args, **kwargs):
        return {
            "found_information": True,
            "description": "First description.",
            "known_for": None,
            "highlights": [],
            "things_to_do": [],
            "important_facts": [],
            "practical_info": None,
            "warnings": [],
            "source_urls": ["https://example.com/review"],
        }

    _run(db, location, monkeypatch, _first)

    def _second(*args, **kwargs):
        return {
            "found_information": True,
            "description": "Second, updated description.",
            "known_for": None,
            "highlights": [],
            "things_to_do": [],
            "important_facts": [],
            "practical_info": None,
            "warnings": [],
            "source_urls": ["https://example.com/review"],
        }

    _run(db, location, monkeypatch, _second)

    rows = db.execute(
        text("select count(*) from location_research_summaries where location_id = :id"),
        {"id": str(location.id)},
    ).scalar()
    assert rows == 1

    summary = place_summary_service.get_summary(db, location.id)
    assert summary.description == "Second, updated description."


def test_c_uncited_summary_is_dropped_not_fabricated(db, location, monkeypatch):
    def _uncited_stub(*args, **kwargs):
        return {
            "found_information": True,
            "description": "A description citing a URL that was never retrieved.",
            "known_for": None,
            "highlights": [],
            "things_to_do": [],
            "important_facts": [],
            "practical_info": None,
            "warnings": [],
            "source_urls": ["https://not-a-real-source.example.com/made-up"],
        }

    _run(db, location, monkeypatch, _uncited_stub)

    summary = place_summary_service.get_summary(db, location.id)
    assert summary is not None
    assert summary.status == "completed"
    assert summary.description is None
    assert summary.source_urls is None


def test_d_summary_failure_does_not_affect_question_generation(db, location, monkeypatch):
    monkeypatch.setattr(
        "app.services.place_questions.perplexity_provider.get_provider",
        lambda: _FakeProvider(),
    )

    def _questions_stub(*args, **kwargs):
        return {
            "questions": [
                {
                    "question_text": "Sources mention carved wooden doors -- can you show us what they look like today?",
                    "contribution_kind": "photo",
                    "context_note": "sources mention carved wooden doors",
                    "source_urls": ["https://example.com/review"],
                    "finding_topic": "interest",
                }
            ],
            "found_information": True,
        }

    def _summary_boom(*args, **kwargs):
        raise PlaceSummaryProviderError("Summary generation service is not configured on the server.")

    monkeypatch.setattr(
        "app.services.place_questions.anthropic_provider.generate_place_questions", _questions_stub
    )
    monkeypatch.setattr(
        "app.services.place_summary_service.anthropic_provider.generate_place_summary", _summary_boom
    )

    research = place_question_service.ensure_researched(db, location.id, force=True)

    # Question generation succeeded despite the summary step failing.
    assert research.status == "completed"
    from app.db.models.place_question import PlaceQuestion

    questions = db.execute(
        select(PlaceQuestion).where(PlaceQuestion.location_id == location.id)
    ).scalars().all()
    assert len(questions) == 1

    # The summary attempt is honestly recorded as failed, not silently dropped
    # or left crashing the whole research run.
    summary = place_summary_service.get_summary(db, location.id)
    assert summary is not None
    assert summary.status == "failed"
    assert summary.error_message


def test_e_summary_generation_never_creates_category_knowledge(db, location, monkeypatch):
    def _summary_stub(*args, **kwargs):
        return {
            "found_information": True,
            "description": "A description.",
            "known_for": None,
            "highlights": [],
            "things_to_do": [],
            "important_facts": [],
            "practical_info": None,
            "warnings": [],
            "source_urls": ["https://example.com/review"],
        }

    _run(db, location, monkeypatch, _summary_stub)

    knowledge_rows = db.execute(
        select(CategoryKnowledge).where(CategoryKnowledge.location_id == location.id)
    ).scalars().all()
    assert knowledge_rows == []
