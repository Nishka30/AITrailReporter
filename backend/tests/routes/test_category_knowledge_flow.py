"""End-to-end regression coverage for the PRIMARY (category-driven) knowledge
system, against the real dev Postgres database -- no mocking of the DB or of
any business logic under test, matching this backend's established
convention. Covers the full chain:

  Location + category assignment
    -> generate_category_questions_for_location (MISSING -> first-ask)
    -> submit_place_question_answer (-> Submission -> Observation, pending)
    -> observation_moderation.approve (-> CategoryKnowledge.last_verified_at)
    -> coverage state (MISSING -> FRESH)
    -> simulated staleness -> generate_category_questions_for_location
       (STALE -> re-verification question, referencing the SAME knowledge row)
    -> duplicate-generation guards (no redundant questions either time)

Also covers the Observation "exactly one of knowledge_type_id /
category_knowledge_id" CHECK constraint, and that dynamic KnowledgeTypeConfig
creation is disabled by default.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.db.geo import make_point
from app.db.models.category_knowledge import CategoryKnowledge
from app.db.models.location import Location
from app.db.models.location_category import LocationCategory, LocationCategoryAssignment
from app.db.models.observation import Observation
from app.db.models.place_question import PlaceQuestion
from app.db.models.submission import Submission
from app.db.session import SessionLocal
from app.schemas.guide import GuideCreate
from app.services import category_knowledge as category_knowledge_service
from app.services import guides as guide_service
from app.services import observation_moderation as observation_moderation_service
from app.services import place_question_answers as place_question_answer_service
from app.services import place_questions as place_question_service


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
    """Reuses the REAL seeded catalog row (no second category system) --
    'food_drink' is a real theme in category_catalog.py at relevance/priority
    85, well above the coverage threshold."""
    category = db.execute(
        select(LocationCategory).where(
            LocationCategory.kind == "theme", LocationCategory.slug == "food_drink"
        )
    ).scalar_one()
    return category


@pytest.fixture
def location_with_category(db, food_drink_category):
    location = Location(
        name=f"Test Cafe {uuid4().hex[:8]}",
        latitude=27.7,
        longitude=85.3,
        geog=make_point(27.7, 85.3),
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
    db.execute(text("delete from place_questions where location_id = :id"), {"id": str(location.id)})
    db.execute(text("delete from location_category_assignments where location_id = :id"), {"id": str(location.id)})
    db.execute(text("delete from locations where id = :id"), {"id": str(location.id)})
    db.commit()


@pytest.fixture
def guide(db):
    g, _ = guide_service.create_or_get_guide(db, GuideCreate(name=f"CK Test Guide {uuid4().hex[:8]}"))
    db.commit()
    yield g
    db.execute(text("delete from guides where id = :id"), {"id": str(g.id)})
    db.commit()


def _cleanup_submission_chain(db, submission_id):
    db.execute(text("delete from observation_moderation where observation_id in (select id from observations where submission_id = :sid)"), {"sid": str(submission_id)})
    db.execute(text("delete from observations where submission_id = :sid"), {"sid": str(submission_id)})
    db.execute(text("delete from submission_reviews where submission_id = :sid"), {"sid": str(submission_id)})
    db.execute(text("delete from submissions where id = :sid"), {"sid": str(submission_id)})
    db.commit()


def test_full_category_knowledge_lifecycle(db, location_with_category, guide):
    location, assignment = location_with_category
    failures = []

    def check(label, cond):
        if not cond:
            failures.append(label)

    # 1. MISSING -> first-ask question generated.
    created = place_question_service.generate_category_questions_for_location(db, location.id)
    check("first generation call creates exactly 1 question", created == 1)

    question = db.execute(
        select(PlaceQuestion).where(PlaceQuestion.location_id == location.id)
    ).scalar_one()
    check("question targets the right category", question.category_assignment_id == assignment.id)
    check("first-ask question has no verifying_knowledge_id", question.verifying_knowledge_id is None)
    check("volatility is set", question.volatility is not None)

    # 2. Re-running generation must NOT create a duplicate first-ask question.
    created_again = place_question_service.generate_category_questions_for_location(db, location.id)
    check("second generation call creates 0 (duplicate guard)", created_again == 0)

    # 3. Coverage is still MISSING (question exists, no knowledge yet).
    coverage = category_knowledge_service.get_location_coverage(db, location.id)
    food_drink_cov = next(c for c in coverage if c.category_assignment_id == assignment.id)
    check("coverage MISSING before any answer", food_drink_cov.state == category_knowledge_service.CATEGORY_STATE_MISSING)

    # 4. Guide answers -> Submission -> Observation (pending, unverified).
    now = datetime.now(timezone.utc)
    submission, created_flag, _points = place_question_answer_service.submit_place_question_answer(
        db, question.id, guide.id, f"answer-{uuid4().hex[:8]}",
        "They're known for great specialty coffee.", now,
    )
    check("answer created", created_flag)
    db.refresh(submission)
    check("submission carries source_place_question_id", submission.source_place_question_id == question.id)

    observation = db.execute(
        select(Observation).where(Observation.submission_id == submission.id)
    ).scalar_one()
    check("observation has category_knowledge_id set", observation.category_knowledge_id is not None)
    check("observation has NO knowledge_type_id (category path bypasses hazard typing)", observation.knowledge_type_id is None)

    knowledge_item = db.get(CategoryKnowledge, observation.category_knowledge_id)
    check("knowledge item created but NOT yet verified", knowledge_item.last_verified_at is None)

    coverage = category_knowledge_service.get_location_coverage(db, location.id)
    food_drink_cov = next(c for c in coverage if c.category_assignment_id == assignment.id)
    check("coverage STILL missing while unverified (anti-gaming rule)", food_drink_cov.state == category_knowledge_service.CATEGORY_STATE_MISSING)

    # 5. Moderation approves -> THIS is what sets last_verified_at.
    observation_moderation_service.approve(db, observation.id, "test-admin")
    db.refresh(knowledge_item)
    check("last_verified_at set only after moderation approval", knowledge_item.last_verified_at is not None)

    coverage = category_knowledge_service.get_location_coverage(db, location.id)
    food_drink_cov = next(c for c in coverage if c.category_assignment_id == assignment.id)
    check("coverage FRESH after verification", food_drink_cov.state == category_knowledge_service.CATEGORY_STATE_FRESH)

    # 6. Simulate staleness by backdating last_verified_at past the snapshot
    #    freshness_duration_hours (never re-deriving the duration live).
    knowledge_item.last_verified_at = now - timedelta(hours=knowledge_item.freshness_duration_hours + 1)
    db.commit()

    coverage = category_knowledge_service.get_location_coverage(db, location.id)
    food_drink_cov = next(c for c in coverage if c.category_assignment_id == assignment.id)
    check("coverage STALE once past freshness_duration_hours", food_drink_cov.state == category_knowledge_service.CATEGORY_STATE_STALE)

    # 7. Generation now produces a RE-VERIFICATION question referencing the
    #    SAME knowledge item -- never a duplicate CategoryKnowledge row.
    created_reverify = place_question_service.generate_category_questions_for_location(db, location.id)
    check("stale knowledge produces exactly 1 re-verification question", created_reverify == 1)

    reverify_question = db.execute(
        select(PlaceQuestion).where(
            PlaceQuestion.verifying_knowledge_id == knowledge_item.id
        )
    ).scalar_one()
    check("re-verification question targets the SAME knowledge item", reverify_question.verifying_knowledge_id == knowledge_item.id)
    check("re-verification question text is NOT a verbatim repeat", reverify_question.question_text != question.question_text)

    # 8. Re-running generation again must not duplicate the re-verification question.
    created_reverify_again = place_question_service.generate_category_questions_for_location(db, location.id)
    check("re-running generation creates 0 more (duplicate guard for re-verification)", created_reverify_again == 0)

    only_one_category_knowledge_row = db.execute(
        select(CategoryKnowledge).where(CategoryKnowledge.category_assignment_id == assignment.id)
    ).scalars().all()
    check("still exactly ONE CategoryKnowledge row (never duplicated on staleness)", len(only_one_category_knowledge_row) == 1)

    _cleanup_submission_chain(db, submission.id)

    if failures:
        pytest.fail("Failures: " + "; ".join(failures))


def test_observation_requires_exactly_one_knowledge_target(db, location_with_category, guide):
    """The CHECK constraint: an Observation must reference exactly one of
    knowledge_type_id / category_knowledge_id -- never both, never neither."""
    location, _assignment = location_with_category
    submission = Submission(
        guide_id=guide.id,
        client_submission_id=f"neither-{uuid4().hex[:8]}",
        submission_type="explore",
        raw_text="test",
        latitude=27.7,
        longitude=85.3,
        location_source="gps_live",
        occurred_at=datetime.now(timezone.utc),
        occurred_at_precision="exact",
        date_source="device",
        submitted_at=datetime.now(timezone.utc),
        status="received",
    )
    db.add(submission)
    db.flush()

    bad_observation = Observation(
        submission_id=submission.id,
        guide_id=guide.id,
        knowledge_type_id=None,
        category_knowledge_id=None,
        value={"x": 1},
        observed_at=datetime.now(timezone.utc),
    )
    db.add(bad_observation)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()

    db.execute(text("delete from submissions where id = :id"), {"id": str(submission.id)})
    db.commit()


def test_dynamic_knowledge_type_creation_disabled_by_default():
    assert settings.dynamic_knowledge_type_creation_enabled is False
