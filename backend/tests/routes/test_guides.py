"""Coverage for the guide `brands` field: a guide may belong to zero or more
of the four controlled brand codes (BCT, HW, TH, PH), set at creation and
later edited via PATCH.

Runs against the real dev Postgres database (SessionLocal) and the real
FastAPI app via TestClient, matching this backend's established testing
convention for guide-adjacent routes (see tests/routes/test_submission_photos.py):
no mocking of the DB.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import SessionLocal
from app.main import app

client = TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _create_guide(db, **overrides):
    payload = {"name": f"Brand Test Guide {uuid4().hex[:8]}", **overrides}
    response = client.post("/api/v1/guides", json=payload)
    return response


@pytest.fixture
def cleanup_guides(db):
    """Yields nothing; just guarantees any guide id appended to this list is
    deleted after the test, mirroring test_submission_photos.py's manual
    teardown convention (no conftest.py exists in this suite)."""
    created_ids: list[str] = []
    yield created_ids
    for guide_id in created_ids:
        db.execute(text("delete from guides where id = :id"), {"id": guide_id})
    db.commit()


def test_create_guide_with_single_brand(db, cleanup_guides):
    response = _create_guide(db, brands=["BCT"])
    assert response.status_code == 201
    body = response.json()
    cleanup_guides.append(body["id"])
    assert body["brands"] == ["BCT"]


def test_create_guide_with_multiple_brands(db, cleanup_guides):
    response = _create_guide(db, brands=["BCT", "HW"])
    assert response.status_code == 201
    body = response.json()
    cleanup_guides.append(body["id"])
    assert body["brands"] == ["BCT", "HW"]


def test_create_guide_rejects_invalid_brand(db, cleanup_guides):
    response = _create_guide(db, brands=["BCT", "NOT_A_BRAND"])
    assert response.status_code == 422
    assert "Unknown brand" in response.text


def test_create_guide_rejects_empty_brand_list(db, cleanup_guides):
    response = _create_guide(db, brands=[])
    assert response.status_code == 422
    assert "At least one brand" in response.text


def test_create_guide_deduplicates_repeated_brands(db, cleanup_guides):
    response = _create_guide(db, brands=["BCT", "BCT", "HW"])
    assert response.status_code == 201
    body = response.json()
    cleanup_guides.append(body["id"])
    assert body["brands"] == ["BCT", "HW"]


def test_existing_guide_with_no_brand_stays_null(db, cleanup_guides):
    """A guide created before this feature (or by any caller that simply
    omits brands) must keep working exactly as before -- brands is None, not
    an invented default."""
    response = _create_guide(db)
    assert response.status_code == 201
    body = response.json()
    cleanup_guides.append(body["id"])
    assert body["brands"] is None


def test_profile_get_returns_brands(db, cleanup_guides):
    created = _create_guide(db, brands=["TH"]).json()
    cleanup_guides.append(created["id"])

    response = client.get(f"/api/v1/guides/{created['id']}")
    assert response.status_code == 200
    assert response.json()["brands"] == ["TH"]


def test_brands_persist_across_fetches(db, cleanup_guides):
    created = _create_guide(db, brands=["PH", "TH"]).json()
    cleanup_guides.append(created["id"])

    first = client.get(f"/api/v1/guides/{created['id']}").json()
    second = client.get(f"/api/v1/guides/{created['id']}").json()
    assert first["brands"] == second["brands"] == ["PH", "TH"]


def test_update_guide_brands(db, cleanup_guides):
    created = _create_guide(db, brands=["BCT"]).json()
    cleanup_guides.append(created["id"])

    response = client.patch(f"/api/v1/guides/{created['id']}", json={"brands": ["HW", "PH"]})
    assert response.status_code == 200
    assert response.json()["brands"] == ["HW", "PH"]


def test_update_guide_rejects_invalid_brand(db, cleanup_guides):
    created = _create_guide(db, brands=["BCT"]).json()
    cleanup_guides.append(created["id"])

    response = client.patch(f"/api/v1/guides/{created['id']}", json={"brands": ["XX"]})
    assert response.status_code == 422
    # The guide's brands must be unchanged after a rejected update.
    assert client.get(f"/api/v1/guides/{created['id']}").json()["brands"] == ["BCT"]


def test_update_guide_rejects_empty_brand_list(db, cleanup_guides):
    created = _create_guide(db, brands=["BCT"]).json()
    cleanup_guides.append(created["id"])

    response = client.patch(f"/api/v1/guides/{created['id']}", json={"brands": []})
    assert response.status_code == 422
    assert client.get(f"/api/v1/guides/{created['id']}").json()["brands"] == ["BCT"]


def test_update_guide_name_only_leaves_brands_untouched(db, cleanup_guides):
    created = _create_guide(db, brands=["HW"]).json()
    cleanup_guides.append(created["id"])

    response = client.patch(f"/api/v1/guides/{created['id']}", json={"name": "Renamed Guide"})
    assert response.status_code == 200
    assert response.json()["brands"] == ["HW"]


def test_update_with_only_brands_is_accepted(db, cleanup_guides):
    """brands alone satisfies GuideUpdate's "at least one field" requirement
    -- it must not need a name/phone_number to accompany it."""
    created = _create_guide(db, brands=["BCT"]).json()
    cleanup_guides.append(created["id"])

    response = client.patch(f"/api/v1/guides/{created['id']}", json={"brands": ["TH"]})
    assert response.status_code == 200
    assert response.json()["brands"] == ["TH"]


def test_update_with_no_fields_is_rejected(db, cleanup_guides):
    created = _create_guide(db, brands=["BCT"]).json()
    cleanup_guides.append(created["id"])

    response = client.patch(f"/api/v1/guides/{created['id']}", json={})
    assert response.status_code == 422
