"""End-to-end regression coverage for Part 1 of the knowledge-architecture
hardening pass (category-gap question generation grounded in Perplexity
research), against the real dev Postgres database -- no mocking of the DB or
of any business logic under test. Only the two external providers
(Perplexity, Anthropic) are monkeypatched, matching this backend's
established convention (see test_category_knowledge_flow.py).

Covers the five required cases:
  A. existing relevant research -> reused, no new Perplexity call
  B. existing research irrelevant -> exactly one targeted query performed
  C. Perplexity unavailable -> deterministic question still generated
  D. same (location, category) -> research reused, no duplicate rows
  E. research findings never directly create CategoryKnowledge
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.db.geo import make_point
from app.db.models.category_knowledge import CategoryKnowledge
from app.db.models.location import Location
from app.db.models.location_category import LocationCategory, LocationCategoryAssignment
from app.db.models.place_question import PlaceQuestion
from app.db.models.place_research_finding import PlaceResearchFinding
from app.db.session import SessionLocal
from app.services import category_research as category_research_service
from app.services import place_questions as place_question_service
from app.services.place_question_research import anthropic_provider
from app.services.research.base import ResearchFinding, ResearchProviderError, ResearchSource


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def food_drink_category(db):
    return db.execute(
        select(LocationCategory).where(
            LocationCategory.kind == "theme", LocationCategory.slug == "food_drink"
        )
    ).scalar_one()


@pytest.fixture
def location_with_category(db, food_drink_category):
    location = Location(
        name=f"Test Bistro {uuid4().hex[:8]}",
        latitude=27.71,
        longitude=85.31,
        geog=make_point(27.71, 85.31),
        source="manual",
    )
    db.add(location)
    db.flush()
    assignment = LocationCategoryAssignment(
        location_id=location.id,
        category_id=food_drink_category.id,
        kind="theme",
        relevance=90,
        confidence=0.9,
        is_primary=True,
        source="manual",
    )
    db.add(assignment)
    db.commit()
    db.refresh(location)
    db.refresh(assignment)
    yield location, assignment

    db.execute(text("delete from place_research_findings where location_id = :id"), {"id": str(location.id)})
    db.execute(text("delete from category_knowledge where location_id = :id"), {"id": str(location.id)})
    db.execute(text("delete from place_questions where location_id = :id"), {"id": str(location.id)})
    db.execute(text("delete from location_category_assignments where location_id = :id"), {"id": str(location.id)})
    db.execute(text("delete from locations where id = :id"), {"id": str(location.id)})
    db.commit()


def _grounded_question_stub(place_name, category_display_name, finding_summary, source_urls):
    return f"Sources say {place_name} is known for its drinks -- is that still true?"


def test_a_existing_relevant_research_reused_no_new_perplexity_call(db, location_with_category, monkeypatch):
    location, assignment = location_with_category

    finding = PlaceResearchFinding(
        location_id=location.id,
        research_id=None,
        topic="interest",
        query_text="stub",
        provider="perplexity",
        model="sonar",
        summary="Regulars say the food and drink here, especially the coffee, is the main draw.",
        source_urls=["https://example.com/review"],
        source_titles=["A review"],
        retrieved_at=datetime.now(timezone.utc),
    )
    db.add(finding)
    db.commit()

    def _fail_if_called():
        raise AssertionError("Perplexity must not be called when an existing finding is relevant")

    monkeypatch.setattr(
        "app.services.category_research.perplexity_provider.get_provider", _fail_if_called
    )
    monkeypatch.setattr(anthropic_provider, "generate_category_question", _grounded_question_stub)

    created = place_question_service.generate_category_questions_for_location(db, location.id)
    assert created == 1

    question = db.execute(
        select(PlaceQuestion).where(PlaceQuestion.location_id == location.id)
    ).scalar_one()
    assert question.source_finding_id == finding.id
    assert "drinks" in question.question_text


def test_b_existing_research_irrelevant_triggers_targeted_query(db, location_with_category, monkeypatch):
    location, assignment = location_with_category

    unrelated = PlaceResearchFinding(
        location_id=location.id,
        research_id=None,
        topic="interest",
        query_text="stub",
        provider="perplexity",
        model="sonar",
        summary="This spot is known for its unusual architecture and a mural on the north wall.",
        source_urls=["https://example.com/architecture"],
        retrieved_at=datetime.now(timezone.utc),
    )
    db.add(unrelated)
    db.commit()

    targeted_calls = []

    class _FakeProvider:
        def run_query(self, query, *, topic, recency=None):
            targeted_calls.append((query, topic))
            return ResearchFinding(
                topic=topic,
                query=query,
                summary="Reviewers specifically mention the food and drink menu here as excellent.",
                provider="perplexity",
                model="sonar",
                retrieved_at=datetime.now(timezone.utc),
                sources=[ResearchSource(url="https://example.com/menu")],
            )

    monkeypatch.setattr(
        "app.services.category_research.perplexity_provider.get_provider",
        lambda: _FakeProvider(),
    )
    monkeypatch.setattr(anthropic_provider, "generate_category_question", _grounded_question_stub)

    created = place_question_service.generate_category_questions_for_location(db, location.id)
    assert created == 1
    assert len(targeted_calls) == 1
    assert targeted_calls[0][1] == "category:food_drink"

    targeted_row = db.execute(
        select(PlaceResearchFinding).where(
            PlaceResearchFinding.location_id == location.id,
            PlaceResearchFinding.topic == "category:food_drink",
        )
    ).scalar_one()
    assert "food and drink menu" in targeted_row.summary


def test_c_perplexity_unavailable_falls_back_to_deterministic_question(db, location_with_category, monkeypatch):
    location, assignment = location_with_category

    def _raise_unavailable():
        raise ResearchProviderError("Web research is not configured on the server.")

    monkeypatch.setattr(
        "app.services.category_research.perplexity_provider.get_provider", _raise_unavailable
    )

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("Anthropic must not be called when there is no finding to ground on")

    monkeypatch.setattr(anthropic_provider, "generate_category_question", _fail_if_called)

    created = place_question_service.generate_category_questions_for_location(db, location.id)
    assert created == 1

    question = db.execute(
        select(PlaceQuestion).where(PlaceQuestion.location_id == location.id)
    ).scalar_one()
    assert question.source_finding_id is None
    assert question.question_text == place_question_service._build_first_ask_text(
        location.name, "Food & Drink"
    )


def test_d_same_location_category_research_reused_no_duplicate_rows(db, location_with_category, monkeypatch):
    location, assignment = location_with_category

    call_count = {"n": 0}

    class _FakeProvider:
        def run_query(self, query, *, topic, recency=None):
            call_count["n"] += 1
            return ResearchFinding(
                topic=topic,
                query=query,
                summary="Reviewers specifically mention the food and drink menu here as excellent.",
                provider="perplexity",
                model="sonar",
                retrieved_at=datetime.now(timezone.utc),
                sources=[ResearchSource(url="https://example.com/menu")],
            )

    monkeypatch.setattr(
        "app.services.category_research.perplexity_provider.get_provider",
        lambda: _FakeProvider(),
    )

    first = category_research_service.get_or_create_category_finding(
        db, location, "food_drink", "Food & Drink"
    )
    second = category_research_service.get_or_create_category_finding(
        db, location, "food_drink", "Food & Drink"
    )
    assert call_count["n"] == 1
    assert first is not None and second is not None
    assert first.id == second.id

    rows = db.execute(
        select(PlaceResearchFinding).where(
            PlaceResearchFinding.location_id == location.id,
            PlaceResearchFinding.topic == "category:food_drink",
        )
    ).scalars().all()
    assert len(rows) == 1


def test_e_research_findings_never_directly_create_category_knowledge(db, location_with_category, monkeypatch):
    location, assignment = location_with_category
    monkeypatch.setattr(anthropic_provider, "generate_category_question", _grounded_question_stub)

    place_question_service.generate_category_questions_for_location(db, location.id)

    knowledge_rows = db.execute(
        select(CategoryKnowledge).where(CategoryKnowledge.location_id == location.id)
    ).scalars().all()
    assert knowledge_rows == []

    questions = db.execute(
        select(PlaceQuestion).where(PlaceQuestion.location_id == location.id)
    ).scalars().all()
    assert len(questions) == 1
