"""Regression coverage for the Admin "supersede" volatility override --
category_knowledge.py::resolve_conflict. The Admin may only ever choose the
volatility CLASS (defaulting to the existing knowledge item's own class); the
backend alone maps that class to freshness_duration_hours via
category_knowledge_policy.resolve_freshness_duration_hours -- there is no
path here that accepts a raw duration from a client.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.db.geo import make_point
from app.db.models.category_knowledge import CategoryKnowledge
from app.db.models.location import Location
from app.db.models.location_category import LocationCategory, LocationCategoryAssignment
from app.db.models.observation import Observation
from app.db.models.submission import Submission
from app.db.session import SessionLocal
from app.schemas.guide import GuideCreate
from app.services import category_knowledge as category_knowledge_service
from app.services import category_knowledge_policy
from app.services import guides as guide_service
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
        name=f"Test Bakery {uuid4().hex[:8]}",
        latitude=27.73,
        longitude=85.33,
        geog=make_point(27.73, 85.33),
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
        db, GuideCreate(name=f"CK-Resolve {uuid4().hex[:8]}")
    )
    db.commit()
    yield g

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


def _verified_item(db, location, assignment, knowledge_text, volatility="MEDIUM"):
    item = category_knowledge_service.create_knowledge_item(
        db,
        location_id=location.id,
        category_assignment_id=assignment.id,
        knowledge_text=knowledge_text,
        volatility=volatility,
    )
    category_knowledge_service.mark_verified(db, item.id, datetime.now(timezone.utc))
    db.commit()
    db.refresh(item)
    return item


def _open_conflict(db, guide, item, new_answer_text):
    now = datetime.now(timezone.utc)
    submission = Submission(
        guide_id=guide.id,
        client_submission_id=f"resolve-{uuid4().hex[:8]}",
        submission_type="answer",
        raw_text=new_answer_text,
        latitude=27.73,
        longitude=85.33,
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
        value={"answer_text": new_answer_text},
        confidence=None,
        evidence=new_answer_text,
        observed_at=now,
    )
    db.add(observation)
    db.flush()
    observation_moderation_service.ensure_pending_moderation(db, observation.id)

    conflict = category_knowledge_service.record_conflict(
        db, category_knowledge_id=item.id, observation_id=observation.id, new_answer_text=new_answer_text
    )
    db.commit()
    db.refresh(conflict)
    return conflict


def test_default_volatility_reused_when_no_override(db, location_with_category, guide):
    location, assignment = location_with_category
    item = _verified_item(db, location, assignment, "The bakery is open 24 hours.", volatility="LOW")
    conflict = _open_conflict(db, guide, item, "Now closes at 8 PM.")

    resolved = category_knowledge_service.resolve_conflict(
        db, conflict.id, resolution="superseded", resolved_by="test-admin",
        new_knowledge_text="The bakery closes at 8 PM.",
    )

    new_item = db.get(CategoryKnowledge, resolved.resolved_knowledge_id)
    assert new_item.volatility == "LOW"
    assert new_item.freshness_duration_hours == category_knowledge_policy.VOLATILITY_DURATIONS_HOURS["LOW"]


def test_admin_override_volatility_is_used(db, location_with_category, guide):
    location, assignment = location_with_category
    item = _verified_item(db, location, assignment, "The bakery is open 24 hours.", volatility="LOW")
    conflict = _open_conflict(db, guide, item, "Now closes at 8 PM.")

    resolved = category_knowledge_service.resolve_conflict(
        db, conflict.id, resolution="superseded", resolved_by="test-admin",
        new_knowledge_text="The bakery closes at 8 PM.", volatility="VERY_HIGH",
    )

    new_item = db.get(CategoryKnowledge, resolved.resolved_knowledge_id)
    assert new_item.volatility == "VERY_HIGH"


@pytest.mark.parametrize("volatility", list(category_knowledge_policy.VOLATILITY_CLASSES))
def test_duration_mapping_matches_policy_for_every_class(db, location_with_category, guide, volatility):
    location, assignment = location_with_category
    item = _verified_item(db, location, assignment, "The bakery is open 24 hours.", volatility="MEDIUM")
    conflict = _open_conflict(db, guide, item, "Now closes at 8 PM.")

    resolved = category_knowledge_service.resolve_conflict(
        db, conflict.id, resolution="superseded", resolved_by="test-admin",
        new_knowledge_text="The bakery closes at 8 PM.", volatility=volatility,
    )

    new_item = db.get(CategoryKnowledge, resolved.resolved_knowledge_id)
    assert new_item.freshness_duration_hours == category_knowledge_policy.VOLATILITY_DURATIONS_HOURS[volatility]


def test_old_knowledge_remains_superseded_and_new_is_verified(db, location_with_category, guide):
    location, assignment = location_with_category
    item = _verified_item(db, location, assignment, "The bakery is open 24 hours.", volatility="LOW")
    conflict = _open_conflict(db, guide, item, "Now closes at 8 PM.")

    resolved = category_knowledge_service.resolve_conflict(
        db, conflict.id, resolution="superseded", resolved_by="test-admin",
        new_knowledge_text="The bakery closes at 8 PM.", volatility="HIGH",
    )

    db.refresh(item)
    assert item.active is False
    assert item.superseded_by_id == resolved.resolved_knowledge_id
    assert item.knowledge_text == "The bakery is open 24 hours."  # never mutated in place

    new_item = db.get(CategoryKnowledge, resolved.resolved_knowledge_id)
    assert new_item.active is True
    assert new_item.last_verified_at is not None
    assert new_item.knowledge_text == "The bakery closes at 8 PM."

    assert resolved.status == "resolved"
    assert resolved.resolution == "superseded"


def test_invalid_volatility_override_is_rejected(db, location_with_category, guide):
    location, assignment = location_with_category
    item = _verified_item(db, location, assignment, "The bakery is open 24 hours.", volatility="LOW")
    conflict = _open_conflict(db, guide, item, "Now closes at 8 PM.")

    with pytest.raises(ValueError):
        category_knowledge_service.resolve_conflict(
            db, conflict.id, resolution="superseded", resolved_by="test-admin",
            new_knowledge_text="The bakery closes at 8 PM.", volatility="EXTREMELY_HIGH",
        )

    db.refresh(item)
    assert item.active is True  # rejected override must not mutate anything
