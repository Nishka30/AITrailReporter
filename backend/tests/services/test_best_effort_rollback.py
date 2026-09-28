"""Regression coverage for a BLOCKER found in the pre-launch production
audit: several "best-effort, never raise" enrichment wrappers swallowed an
exception WITHOUT calling db.rollback() first.

Under SQLAlchemy 2.0 (confirmed sqlalchemy==2.0.36 in requirements.txt), once
a flush/statement fails inside a session, the session is left needing an
explicit rollback -- any further use of it raises PendingRollbackError, it is
NOT automatically recovered. These wrappers run on the SAME session the
caller keeps using afterwards (e.g. create_or_get_submission calls
maybe_trigger_extraction as its very last step, then the route builds the
response from that same session) -- so a missing rollback here turned an
already-successfully-committed submission into a client-visible 500 on the
very next query, for a reason completely unrelated to the guide's request.

Covers the three call sites found with this gap:
  - extractions.maybe_trigger_extraction
  - poi_discovery.maybe_ensure_discovered
  - places.category_assignment.maybe_assign_categories

Each test forces a REAL, session-poisoning database error (not just a plain
Python exception) inside the wrapped call, then asserts the session is
immediately usable again afterward.
"""

from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.db.geo import make_point
from app.db.models.location import Location
from app.db.session import SessionLocal
from app.schemas.guide import GuideCreate
from app.schemas.submission import SubmissionCreate
from app.services import extractions as extraction_service
from app.services import guides as guide_service
from app.services import place_questions as place_question_service
from app.services import poi_discovery as poi_discovery_service
from app.services import submissions as submission_service
from app.services import transcriptions as transcription_service
from app.services.places import category_assignment as category_assignment_service


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _poison_session(db):
    """Forces a real, session-poisoning DB error -- the same class of failure
    (an error deep in a flush/query) these wrappers must survive, not merely
    a plain Python exception raised before ever touching the DB."""
    with pytest.raises(DBAPIError):
        db.execute(text("SELECT * FROM this_table_does_not_exist_at_all"))


def test_maybe_ensure_discovered_leaves_session_usable_after_failure(db, monkeypatch):
    def _boom(*args, **kwargs):
        _poison_session(db)
        raise RuntimeError("simulated failure deep in discovery")

    monkeypatch.setattr(poi_discovery_service.location_service, "find_nearest_location", _boom)

    # Must not raise -- this is the best-effort contract.
    poi_discovery_service.maybe_ensure_discovered(db, 12.9, 77.6)

    # If maybe_ensure_discovered failed to roll back, this raises
    # PendingRollbackError instead of returning a result.
    db.execute(select(1))


def test_maybe_assign_categories_leaves_session_usable_after_failure(db, monkeypatch):
    location = Location(
        name=f"Rollback Test Location {uuid4().hex[:8]}",
        latitude=12.9,
        longitude=77.6,
        geog=make_point(12.9, 77.6),
        source="manual",
    )
    db.add(location)
    db.commit()
    db.refresh(location)

    def _boom(*args, **kwargs):
        _poison_session(db)
        raise RuntimeError("simulated failure deep in category assignment")

    monkeypatch.setattr(category_assignment_service, "assign_categories", _boom)

    try:
        category_assignment_service.maybe_assign_categories(db, location)
        db.execute(select(1))
    finally:
        db.execute(text("delete from locations where id = :id"), {"id": str(location.id)})
        db.commit()


def test_maybe_trigger_extraction_leaves_session_usable_after_failure(db, monkeypatch):
    guide, _ = guide_service.create_or_get_guide(
        db, GuideCreate(name=f"Rollback Test Guide {uuid4().hex[:8]}")
    )
    db.commit()

    submission, _created = submission_service.create_or_get_submission(
        db,
        SubmissionCreate(
            guide_id=guide.id,
            client_submission_id=str(uuid4()),
            capture_type="note",
            text_content="A note with real text, so resolve_source_text succeeds.",
        ),
    )
    db.commit()

    try:
        # start_extraction is idempotent (see its own docstring), so calling
        # maybe_trigger_extraction a second time -- now patched to explode
        # deep inside, after the source text is already resolved -- exercises
        # exactly the try/except this regression test targets.
        def _boom(*args, **kwargs):
            _poison_session(db)
            raise RuntimeError("simulated failure deep in extraction")

        monkeypatch.setattr(extraction_service, "start_extraction", _boom)

        extraction_service.maybe_trigger_extraction(db, submission.id)

        # If maybe_trigger_extraction failed to roll back, this raises
        # PendingRollbackError instead of returning a result.
        db.execute(select(1))
    finally:
        db.execute(text("delete from submissions where id = :id"), {"id": str(submission.id)})
        db.execute(text("delete from guides where id = :id"), {"id": str(guide.id)})
        db.commit()


def test_schedule_transcription_leaves_session_usable_after_failure(db, monkeypatch):
    """schedule_transcription() is called by routes/submissions.py and then
    the SAME request-scoped session is immediately reused to build the
    response (submission_service.build_submission_read). A claim failure that
    doesn't roll back would turn an already-saved submission into a
    client-visible 500 for a reason unrelated to the guide's request --
    identical in shape to the extraction/discovery/category-assignment gaps
    this audit found, just in transcriptions.py instead."""
    guide, _ = guide_service.create_or_get_guide(
        db, GuideCreate(name=f"Rollback Test Guide {uuid4().hex[:8]}")
    )
    db.commit()

    submission, _created = submission_service.create_or_get_submission(
        db,
        SubmissionCreate(
            guide_id=guide.id,
            client_submission_id=str(uuid4()),
            capture_type="note",
            text_content="Irrelevant to this test -- only the session state matters.",
        ),
    )
    db.commit()

    try:
        def _boom(*args, **kwargs):
            _poison_session(db)
            raise RuntimeError("simulated failure deep in transcription claiming")

        monkeypatch.setattr(transcription_service, "claim_transcription", _boom)

        outcome = transcription_service.schedule_transcription(None, db, submission.id)
        assert outcome == "failed"

        # If schedule_transcription failed to roll back, this raises
        # PendingRollbackError instead of returning a result -- exactly what
        # would otherwise turn the caller's next query into a false 500.
        db.execute(select(1))
    finally:
        db.execute(text("delete from submissions where id = :id"), {"id": str(submission.id)})
        db.execute(text("delete from guides where id = :id"), {"id": str(guide.id)})
        db.commit()


def test_maybe_ensure_researched_leaves_session_usable_after_failure(db, monkeypatch):
    location = Location(
        name=f"Rollback Test Location {uuid4().hex[:8]}",
        latitude=12.9,
        longitude=77.6,
        geog=make_point(12.9, 77.6),
        source="manual",
    )
    db.add(location)
    db.commit()
    db.refresh(location)

    def _boom(*args, **kwargs):
        _poison_session(db)
        raise RuntimeError("simulated failure deep in place-question research")

    monkeypatch.setattr(place_question_service, "ensure_researched", _boom)

    try:
        place_question_service.maybe_ensure_researched(db, location.id)
        db.execute(select(1))
    finally:
        db.execute(text("delete from locations where id = :id"), {"id": str(location.id)})
        db.commit()
