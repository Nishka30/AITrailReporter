"""Regression coverage for the force-research admin gate.

Context: POST /api/v1/locations/{id}/popular-questions/research previously had
no auth at all, so `?force=True` -- which deliberately bypasses the 30-day
freshness window -- could be called by anyone, in a loop, generating real
Perplexity + Anthropic spend with no bound. Fixed by reusing the SAME admin
token dependency every other privileged write in this backend already uses
(app/core/admin_auth.py::require_admin) -- no new auth mechanism.

These tests run against the real dev Postgres database (SessionLocal), same
convention as the rest of this backend's tests: no mocking of the DB or of
`ensure_researched`'s own locking logic. What IS stubbed is the external
provider call (`perplexity_provider.get_provider`) -- these tests must never
spend real money -- and, for the pure-auth tests, `ensure_researched` itself,
since those tests are about the HTTP boundary, not the research flow.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.geo import make_point
from app.db.models.location import Location
from app.db.models.place_question import PlaceQuestionResearch
from app.db.session import SessionLocal
from app.main import app
from app.services import place_questions as place_question_service

client = TestClient(app)

_RESEARCH_PATH = "/api/v1/locations/{location_id}/popular-questions/research"


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
        name=f"Test Research Auth Location {uuid4().hex[:8]}",
        latitude=27.7172,
        longitude=85.3240,
        geog=make_point(27.7172, 85.3240),
        source="manual",
    )
    db.add(loc)
    db.commit()
    db.refresh(loc)
    yield loc
    db.execute(
        PlaceQuestionResearch.__table__.delete().where(
            PlaceQuestionResearch.location_id == loc.id
        )
    )
    db.execute(Location.__table__.delete().where(Location.id == loc.id))
    db.commit()


# ---------------------------------------------------------------------------
# HTTP-level: unauthorized callers cannot force research
# ---------------------------------------------------------------------------


def test_force_research_with_no_token_is_rejected(location, monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(
        place_question_service, "ensure_researched",
        lambda *a, **k: calls.__setitem__("n", calls["n"] + 1),
    )

    response = client.post(
        _RESEARCH_PATH.format(location_id=location.id), params={"force": True}
    )

    assert response.status_code == 401
    assert calls["n"] == 0  # never reached the research service at all


def test_force_research_with_wrong_token_is_rejected(location, monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(
        place_question_service, "ensure_researched",
        lambda *a, **k: calls.__setitem__("n", calls["n"] + 1),
    )

    response = client.post(
        _RESEARCH_PATH.format(location_id=location.id),
        params={"force": True},
        headers={"X-Admin-Token": "definitely-not-the-real-token"},
    )

    assert response.status_code == 401
    assert calls["n"] == 0


# ---------------------------------------------------------------------------
# HTTP-level: an authorized admin can still force research
# ---------------------------------------------------------------------------


def test_force_research_with_correct_admin_token_is_allowed(location, monkeypatch):
    """Proves the route itself is reachable by an admin -- the research
    service is stubbed here (not the auth layer) so this test costs nothing
    and only asserts the auth boundary let the real call through."""
    calls = {"n": 0}

    def fake_ensure_researched(db, location_id, force=False):
        # Return value is discarded by the route (it re-reads the question
        # list separately afterwards) -- only that this was CALLED matters here.
        calls["n"] += 1
        assert force is True

    monkeypatch.setattr(place_question_service, "ensure_researched", fake_ensure_researched)

    response = client.post(
        _RESEARCH_PATH.format(location_id=location.id),
        params={"force": True},
        headers={"X-Admin-Token": settings.admin_api_token, "X-Admin-Name": "test-admin"},
    )

    assert response.status_code == 200
    assert calls["n"] == 1


# ---------------------------------------------------------------------------
# The NORMAL, automatic, guide-facing flow must be completely untouched
# ---------------------------------------------------------------------------


def test_guide_popular_questions_is_still_unauthenticated(monkeypatch):
    """GET /guides/{id}/popular-questions -- the background-triggered,
    staleness-gated automatic path -- must still require NO admin token at
    all. This is the one change this fix must never make."""
    from app.services import guides as guide_service
    from app.schemas.guide import GuideCreate

    db = SessionLocal()
    try:
        guide, _ = guide_service.create_or_get_guide(
            db, GuideCreate(name=f"Auth Test Guide {uuid4().hex[:8]}")
        )
        db.commit()
        guide_id = guide.id

        response = client.get(f"/api/v1/guides/{guide_id}/popular-questions")

        assert response.status_code != 401
        assert response.status_code != 403
    finally:
        db.rollback()
        from app.db.models.guide import Guide

        db.execute(Guide.__table__.delete().where(Guide.id == guide_id))
        db.commit()
        db.close()


# ---------------------------------------------------------------------------
# Service-level: the existing processing lock still prevents duplicate calls
# ---------------------------------------------------------------------------


def test_concurrent_research_does_not_duplicate_the_provider_call(db, location, monkeypatch):
    """Simulates a second caller arriving while a first research run is still
    'processing' -- must short-circuit WITHOUT ever reaching the provider,
    exactly as before this change (this fix only added auth in front of the
    route; it must not have touched ensure_researched's own locking at all).
    """
    provider_calls = {"n": 0}

    class _ExplodingProvider:
        name = "perplexity"

        def run_query(self, *a, **k):
            provider_calls["n"] += 1
            raise AssertionError("must not call the provider while another run is processing")

    monkeypatch.setattr(
        place_question_service.perplexity_provider, "get_provider", lambda: _ExplodingProvider()
    )

    # A run is already claimed and genuinely in flight (started just now, well
    # inside the abandoned-run timeout).
    from datetime import datetime, timezone

    in_flight = PlaceQuestionResearch(
        location_id=location.id, status="processing", started_at=datetime.now(timezone.utc)
    )
    db.add(in_flight)
    db.commit()

    result = place_question_service.ensure_researched(db, location.id, force=False)

    assert result.status == "processing"
    assert provider_calls["n"] == 0
