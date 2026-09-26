"""Regression test proving dynamic KnowledgeTypeConfig creation is actually
disabled end-to-end (not just a config default nobody exercises) -- see
app/services/extractions.py's guard around create_or_get_dynamic_type and
app/core/config.py::dynamic_knowledge_type_creation_enabled.

Real dev DB, real extraction pipeline; only the LLM call itself is stubbed
(extract_observations), since the point is proving the BACKEND'S OWN guard
logic, not re-testing Anthropic's API.
"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, text

from app.db.models.knowledge_type_config import KnowledgeTypeConfig
from app.db.models.observation import Observation
from app.db.models.submission import Submission
from app.db.session import SessionLocal
from app.schemas.guide import GuideCreate
from app.services import extractions as extractions_service
from app.services import guides as guide_service

_NEW_TYPE_NAME = "parking_availability_test_probe"


def _fake_extract_observations(source_text, allowed_types, nearest_known_place):
    return {
        "observations": [],
        "new_knowledge_types": [
            {
                "knowledge_type": _NEW_TYPE_NAME,
                "display_name": "Parking Availability",
                "volatility": "days",
                "scope": "point",
                "significance": "practical",
                "value": {"available": True},
                "confidence": 0.8,
                "evidence": "The guide mentioned parking was available near the entrance.",
            }
        ],
    }


def test_dynamic_type_proposal_is_dropped_not_persisted(monkeypatch):
    db = SessionLocal()
    guide = None
    submission = None
    try:
        guide, _ = guide_service.create_or_get_guide(
            db, GuideCreate(name=f"Dyn Type Test Guide {uuid4().hex[:8]}")
        )
        db.commit()

        submission = Submission(
            guide_id=guide.id,
            client_submission_id=f"dyn-type-{uuid4().hex[:8]}",
            submission_type="explore",
            raw_text="There was plenty of parking near the entrance today.",
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
        db.commit()

        monkeypatch.setattr(extractions_service, "extract_observations", _fake_extract_observations)

        extraction, outcome = extractions_service.start_extraction(db, submission.id)

        assert outcome == "completed"
        assert extraction.status == "completed"

        new_type = db.execute(
            select(KnowledgeTypeConfig).where(KnowledgeTypeConfig.knowledge_type == _NEW_TYPE_NAME)
        ).scalar_one_or_none()
        assert new_type is None, "dynamic type creation must be disabled -- no new KnowledgeTypeConfig row"

        observations = list(
            db.execute(select(Observation).where(Observation.submission_id == submission.id)).scalars()
        )
        assert observations == [], "the dropped proposal must not produce an orphan Observation either"
    finally:
        if submission is not None:
            db.execute(text("delete from extractions where submission_id = :sid"), {"sid": str(submission.id)})
            db.execute(text("delete from observations where submission_id = :sid"), {"sid": str(submission.id)})
            db.execute(text("delete from submissions where id = :sid"), {"sid": str(submission.id)})
        db.execute(text("delete from knowledge_type_config where knowledge_type = :t"), {"t": _NEW_TYPE_NAME})
        if guide is not None:
            db.execute(text("delete from guides where id = :id"), {"id": str(guide.id)})
        db.commit()
        db.close()
