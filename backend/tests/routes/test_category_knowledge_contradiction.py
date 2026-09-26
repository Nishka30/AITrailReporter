"""End-to-end regression coverage for Part 2 of the knowledge-architecture
hardening pass (CONFIRMS/CONTRADICTS/UNCERTAIN contradiction handling on
re-verification), against the real dev Postgres database.

knowledge_relation.classify_relation is monkeypatched to a controlled stub
for most of these tests -- the classifier's own text-matching logic is
covered separately in tests/services/test_knowledge_relation.py. What's under
test HERE is the state-machine wiring in observation_moderation.py: given a
known relation, does the right thing happen to CategoryKnowledge,
CategoryKnowledgeConflict, and the Observation/moderation ledger.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.db.geo import make_point
from app.db.models.category_knowledge import CategoryKnowledge
from app.db.models.category_knowledge_conflict import CategoryKnowledgeConflict
from app.db.models.location import Location
from app.db.models.location_category import LocationCategory, LocationCategoryAssignment
from app.db.models.observation import Observation
from app.db.models.submission import Submission
from app.db.session import SessionLocal
from app.schemas.guide import GuideCreate
from app.services import category_knowledge as category_knowledge_service
from app.services import guides as guide_service
from app.services import knowledge_relation
from app.services import observation_moderation as observation_moderation_service


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
        name=f"Test Diner {uuid4().hex[:8]}",
        latitude=27.72,
        longitude=85.32,
        geog=make_point(27.72, 85.32),
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

    db.execute(text("delete from category_knowledge where location_id = :id"), {"id": str(location.id)})
    db.execute(text("delete from location_category_assignments where location_id = :id"), {"id": str(location.id)})
    db.execute(text("delete from locations where id = :id"), {"id": str(location.id)})
    db.commit()


@pytest.fixture
def guide(db):
    g, _ = guide_service.create_or_get_guide(
        db, GuideCreate(name=f"CK-Contra {uuid4().hex[:8]}")
    )
    db.commit()
    yield g

    # Guide-scoped cleanup, in strict FK dependency order -- this fixture's
    # teardown runs BEFORE location_with_category's (both are independent,
    # so pytest tears them down in the reverse of the order the test
    # requested them), so any CategoryKnowledgeConflict/Observation this
    # guide produced must be cleared here first: observations.guide_id
    # CASCADEs, but category_knowledge_conflicts.observation_id is RESTRICT,
    # which would otherwise block the guide delete below.
    db.execute(text(
        "delete from category_knowledge_conflicts where observation_id in "
        "(select id from observations where guide_id = :gid)"
    ), {"gid": str(g.id)})
    db.execute(text(
        "delete from observation_moderation where observation_id in "
        "(select id from observations where guide_id = :gid)"
    ), {"gid": str(g.id)})
    db.execute(text("delete from observations where guide_id = :gid"), {"gid": str(g.id)})
    db.execute(text("delete from submissions where guide_id = :gid"), {"gid": str(g.id)})
    db.execute(text("delete from guides where id = :id"), {"id": str(g.id)})
    db.commit()


def _verified_item(db, location, assignment, knowledge_text, *, verified_at=None):
    item = category_knowledge_service.create_knowledge_item(
        db,
        location_id=location.id,
        category_assignment_id=assignment.id,
        knowledge_text=knowledge_text,
        volatility="MEDIUM",
    )
    category_knowledge_service.mark_verified(db, item.id, verified_at or datetime.now(timezone.utc))
    db.commit()
    db.refresh(item)
    return item


def _reverification_observation(db, guide, item, answer_text):
    now = datetime.now(timezone.utc)
    submission = Submission(
        guide_id=guide.id,
        client_submission_id=f"contra-{uuid4().hex[:8]}",
        submission_type="answer",
        raw_text=answer_text,
        latitude=27.72,
        longitude=85.32,
        location_source="approximate",
        occurred_at=now,
        occurred_at_precision="exact",
        date_source="device",
        submitted_at=now,
        status="received",
    )
    db.add(submission)
    db.flush()

    observation = Observation(
        submission_id=submission.id,
        guide_id=guide.id,
        knowledge_type_id=None,
        category_knowledge_id=item.id,
        value={"answer_text": answer_text},
        confidence=None,
        evidence=answer_text,
        observed_at=now,
    )
    db.add(observation)
    db.flush()
    observation_moderation_service.ensure_pending_moderation(db, observation.id)
    db.commit()
    db.refresh(observation)
    return observation


def test_a_confirming_observation_same_row_no_duplicate(db, location_with_category, guide, monkeypatch):
    location, assignment = location_with_category
    item = _verified_item(db, location, assignment, "Serves great local coffee.")
    original_verified_at = item.last_verified_at

    observation = _reverification_observation(db, guide, item, "Still serves great local coffee.")
    monkeypatch.setattr(
        knowledge_relation, "classify_relation",
        lambda *a, **k: knowledge_relation.RelationResult(knowledge_relation.RELATION_CONFIRMS),
    )

    observation_moderation_service.approve(db, observation.id, "test-admin")
    db.refresh(item)

    assert item.last_verified_at is not None
    assert item.last_verified_at > original_verified_at
    assert item.active is True
    assert item.superseded_by_id is None

    rows = db.execute(
        select(CategoryKnowledge).where(CategoryKnowledge.category_assignment_id == assignment.id)
    ).scalars().all()
    assert len(rows) == 1


def test_b_contradicting_observation_supersedes_preserving_history(db, location_with_category, guide, monkeypatch):
    location, assignment = location_with_category
    item = _verified_item(db, location, assignment, "The diner is open 24 hours.")

    observation = _reverification_observation(db, guide, item, "It actually closes at 10 PM now.")
    monkeypatch.setattr(
        knowledge_relation, "classify_relation",
        lambda *a, **k: knowledge_relation.RelationResult(
            knowledge_relation.RELATION_CONTRADICTS, new_knowledge_text="The diner closes at 10 PM."
        ),
    )

    observation_moderation_service.approve(db, observation.id, "test-admin")
    db.refresh(item)

    assert item.active is False
    assert item.superseded_by_id is not None
    assert item.knowledge_text == "The diner is open 24 hours."  # never overwritten in place

    new_item = db.get(CategoryKnowledge, item.superseded_by_id)
    assert new_item.active is True
    assert new_item.knowledge_text == "The diner closes at 10 PM."
    assert new_item.last_verified_at is not None
    assert new_item.volatility == item.volatility
    assert new_item.freshness_duration_hours == item.freshness_duration_hours

    # The old Observation this all started from is still there, untouched.
    db.refresh(observation)
    assert observation.category_knowledge_id == item.id


def test_c_uncertain_leaves_knowledge_untouched_and_opens_conflict(db, location_with_category, guide, monkeypatch):
    location, assignment = location_with_category
    item = _verified_item(db, location, assignment, "The diner has a rooftop seating area.")
    original_text = item.knowledge_text
    original_verified_at = item.last_verified_at

    observation = _reverification_observation(db, guide, item, "The music here is loud on weekends.")
    monkeypatch.setattr(
        knowledge_relation, "classify_relation",
        lambda *a, **k: knowledge_relation.RelationResult(knowledge_relation.RELATION_UNCERTAIN),
    )

    observation_moderation_service.approve(db, observation.id, "test-admin")
    db.refresh(item)

    assert item.knowledge_text == original_text
    assert item.last_verified_at == original_verified_at
    assert item.active is True
    assert item.superseded_by_id is None

    conflict = db.execute(
        select(CategoryKnowledgeConflict).where(CategoryKnowledgeConflict.observation_id == observation.id)
    ).scalar_one()
    assert conflict.status == "open"
    assert conflict.category_knowledge_id == item.id
    assert conflict.new_answer_text == "The music here is loud on weekends."

    # The Observation itself is preserved, not deleted or altered.
    db.refresh(observation)
    assert observation.value == {"answer_text": "The music here is loud on weekends."}


def test_d_multiple_knowledge_items_only_relevant_one_affected(db, location_with_category, guide, monkeypatch):
    location, assignment = location_with_category
    coffee_item = _verified_item(db, location, assignment, "Serves local coffee.")
    hours_item = _verified_item(db, location, assignment, "Closes at 10 PM.")

    observation = _reverification_observation(db, guide, hours_item, "Yes, still closes at 10 PM.")
    monkeypatch.setattr(
        knowledge_relation, "classify_relation",
        lambda *a, **k: knowledge_relation.RelationResult(knowledge_relation.RELATION_CONFIRMS),
    )

    coffee_verified_before = coffee_item.last_verified_at
    observation_moderation_service.approve(db, observation.id, "test-admin")

    db.refresh(coffee_item)
    db.refresh(hours_item)
    assert coffee_item.last_verified_at == coffee_verified_before  # untouched
    assert hours_item.last_verified_at is not None
    assert hours_item.last_verified_at > coffee_verified_before

    rows = db.execute(
        select(CategoryKnowledge).where(CategoryKnowledge.category_assignment_id == assignment.id)
    ).scalars().all()
    assert len(rows) == 2  # no new row created, no row destroyed


def test_e_stale_confirming_refreshes_same_row(db, location_with_category, guide, monkeypatch):
    location, assignment = location_with_category
    item = _verified_item(
        db, location, assignment, "Serves great local coffee.",
        verified_at=datetime.now(timezone.utc) - timedelta(hours=10_000),
    )
    assert category_knowledge_service.is_stale(item, datetime.now(timezone.utc))

    observation = _reverification_observation(db, guide, item, "Still true, great coffee.")
    monkeypatch.setattr(
        knowledge_relation, "classify_relation",
        lambda *a, **k: knowledge_relation.RelationResult(knowledge_relation.RELATION_CONFIRMS),
    )
    observation_moderation_service.approve(db, observation.id, "test-admin")
    db.refresh(item)

    assert category_knowledge_service.is_fresh(item, datetime.now(timezone.utc))


def test_f_stale_contradicting_creates_replacement(db, location_with_category, guide, monkeypatch):
    location, assignment = location_with_category
    item = _verified_item(
        db, location, assignment, "The diner is open 24 hours.",
        verified_at=datetime.now(timezone.utc) - timedelta(hours=10_000),
    )
    observation = _reverification_observation(db, guide, item, "Now closes at 10 PM.")
    monkeypatch.setattr(
        knowledge_relation, "classify_relation",
        lambda *a, **k: knowledge_relation.RelationResult(
            knowledge_relation.RELATION_CONTRADICTS, new_knowledge_text="The diner closes at 10 PM."
        ),
    )
    observation_moderation_service.approve(db, observation.id, "test-admin")
    db.refresh(item)
    assert item.active is False
    new_item = db.get(CategoryKnowledge, item.superseded_by_id)
    assert category_knowledge_service.is_fresh(new_item, datetime.now(timezone.utc))


def test_g_fresh_contradicting_never_silently_overwritten(db, location_with_category, guide, monkeypatch):
    location, assignment = location_with_category
    item = _verified_item(db, location, assignment, "The diner is open 24 hours.")
    assert category_knowledge_service.is_fresh(item, datetime.now(timezone.utc))

    observation = _reverification_observation(db, guide, item, "Now closes at 10 PM.")
    monkeypatch.setattr(
        knowledge_relation, "classify_relation",
        lambda *a, **k: knowledge_relation.RelationResult(
            knowledge_relation.RELATION_CONTRADICTS, new_knowledge_text="The diner closes at 10 PM."
        ),
    )
    observation_moderation_service.approve(db, observation.id, "test-admin")
    db.refresh(item)

    # The original row's text is never mutated in place -- it is deactivated
    # and superseded, with the ORIGINAL text still intact for audit.
    assert item.knowledge_text == "The diner is open 24 hours."
    assert item.active is False
    assert item.superseded_by_id is not None


def test_h_unmoderated_observation_never_mutates_knowledge(db, location_with_category, guide):
    location, assignment = location_with_category
    item = _verified_item(db, location, assignment, "Serves great local coffee.")
    original_verified_at = item.last_verified_at

    _reverification_observation(db, guide, item, "Still true.")
    # Deliberately never approved.
    db.refresh(item)
    assert item.last_verified_at == original_verified_at
    assert item.active is True


def test_i_repeated_confirmation_no_duplicate_rows(db, location_with_category, guide, monkeypatch):
    location, assignment = location_with_category
    item = _verified_item(db, location, assignment, "Serves great local coffee.")

    monkeypatch.setattr(
        knowledge_relation, "classify_relation",
        lambda *a, **k: knowledge_relation.RelationResult(knowledge_relation.RELATION_CONFIRMS),
    )
    for _ in range(2):
        observation = _reverification_observation(db, guide, item, "Still true.")
        observation_moderation_service.approve(db, observation.id, "test-admin")

    rows = db.execute(
        select(CategoryKnowledge).where(CategoryKnowledge.category_assignment_id == assignment.id)
    ).scalars().all()
    assert len(rows) == 1


def test_j_historical_observations_remain_intact_after_supersession(db, location_with_category, guide, monkeypatch):
    location, assignment = location_with_category
    item = _verified_item(db, location, assignment, "The diner is open 24 hours.")
    first_observation = _reverification_observation(db, guide, item, "Confirmed, open 24 hours.")
    monkeypatch.setattr(
        knowledge_relation, "classify_relation",
        lambda *a, **k: knowledge_relation.RelationResult(knowledge_relation.RELATION_CONFIRMS),
    )
    observation_moderation_service.approve(db, first_observation.id, "test-admin")

    second_observation = _reverification_observation(db, guide, item, "Now closes at 10 PM.")
    monkeypatch.setattr(
        knowledge_relation, "classify_relation",
        lambda *a, **k: knowledge_relation.RelationResult(
            knowledge_relation.RELATION_CONTRADICTS, new_knowledge_text="The diner closes at 10 PM."
        ),
    )
    observation_moderation_service.approve(db, second_observation.id, "test-admin")

    # Both historical Observations still exist, both still point at the
    # ORIGINAL (now superseded) knowledge item -- never rewritten to point at
    # the replacement.
    db.refresh(first_observation)
    db.refresh(second_observation)
    assert first_observation.category_knowledge_id == item.id
    assert second_observation.category_knowledge_id == item.id
