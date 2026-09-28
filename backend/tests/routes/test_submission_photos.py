"""Regression coverage for multi-image support and the storage-error
root-cause fix.

Runs against the real dev Postgres database (SessionLocal) and the real
local-filesystem photo storage backend (get_photo_storage() falls back to it
whenever Supabase credentials aren't configured -- see
app/services/storage/__init__.py), matching this backend's established
testing convention: no mocking of the DB or of attach_photo_to_submission's
own logic. What IS faked is the STORAGE BACKEND itself, for the tests that
need to simulate a storage failure -- a real Supabase outage is not
something a test should depend on being reproducible on demand.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.schemas.guide import GuideCreate
from app.schemas.submission import SubmissionCreate
from app.services import guides as guide_service
from app.services import submissions as submission_service
from app.services.storage import get_photo_storage
from app.services.storage.base import MediaStorage, MediaStorageError, StoredFile

client = TestClient(app)

# A tiny, genuinely valid JPEG signature (FF D8 FF ...) -- passes
# photo_validation.py's magic-byte sniff without needing a real photo file.
_FAKE_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def guide(db):
    g, _ = guide_service.create_or_get_guide(db, GuideCreate(name=f"Photo Test Guide {uuid4().hex[:8]}"))
    db.commit()
    yield g
    db.execute(text("delete from guides where id = :id"), {"id": str(g.id)})
    db.commit()


@pytest.fixture
def explore_submission(db, guide):
    submission, _created = submission_service.create_or_get_submission(
        db,
        SubmissionCreate(
            guide_id=guide.id,
            client_submission_id=str(uuid4()),
            capture_type="explore",
            text_content="Testing multi-photo support.",
        ),
    )
    yield submission
    # CASCADEs to submission_photos/submission_reviews/observations -- see
    # their FK ondelete settings.
    db.execute(text("delete from submissions where id = :id"), {"id": str(submission.id)})
    db.commit()


def test_attach_multiple_distinct_photos(db, explore_submission):
    p1 = submission_service.attach_photo_to_submission(
        db, explore_submission.id, f"client-{uuid4().hex}", _FAKE_JPEG,
        content_type="image/jpeg", original_filename="a.jpg", storage=get_photo_storage(),
    )
    p2 = submission_service.attach_photo_to_submission(
        db, explore_submission.id, f"client-{uuid4().hex}", _FAKE_JPEG,
        content_type="image/jpeg", original_filename="b.jpg", storage=get_photo_storage(),
    )
    assert p1[1] is True and p2[1] is True

    photos = submission_service.list_submission_photos(db, explore_submission.id)
    assert len(photos) == 2
    assert [p.position for p in photos] == [0, 1]
    assert [p.original_filename for p in photos] == ["a.jpg", "b.jpg"]


def test_retry_with_same_client_photo_id_is_idempotent_no_duplicate(db, explore_submission):
    client_photo_id = f"client-{uuid4().hex}"
    submission_service.attach_photo_to_submission(
        db, explore_submission.id, client_photo_id, _FAKE_JPEG,
        content_type="image/jpeg", original_filename="a.jpg", storage=get_photo_storage(),
    )
    # Simulates a retried sync whose original response was lost -- SAME
    # client_photo_id, same bytes, called again.
    _submission, created_again = submission_service.attach_photo_to_submission(
        db, explore_submission.id, client_photo_id, _FAKE_JPEG,
        content_type="image/jpeg", original_filename="a.jpg", storage=get_photo_storage(),
    )
    assert created_again is False

    photos = submission_service.list_submission_photos(db, explore_submission.id)
    assert len(photos) == 1  # never duplicated


def test_client_photo_id_collision_across_submissions_raises_conflict(db, guide, explore_submission):
    client_photo_id = f"client-{uuid4().hex}"
    submission_service.attach_photo_to_submission(
        db, explore_submission.id, client_photo_id, _FAKE_JPEG,
        content_type="image/jpeg", original_filename="a.jpg", storage=get_photo_storage(),
    )

    other_submission, _ = submission_service.create_or_get_submission(
        db,
        SubmissionCreate(
            guide_id=guide.id,
            client_submission_id=str(uuid4()),
            capture_type="memory",
            text_content="A different contribution.",
        ),
    )
    try:
        with pytest.raises(submission_service.PhotoConflictError):
            submission_service.attach_photo_to_submission(
                db, other_submission.id, client_photo_id, _FAKE_JPEG,
                content_type="image/jpeg", original_filename="a.jpg", storage=get_photo_storage(),
            )
    finally:
        db.execute(text("delete from submissions where id = :id"), {"id": str(other_submission.id)})
        db.commit()


def test_exceeding_the_cap_raises_too_many_photos(db, explore_submission, monkeypatch):
    monkeypatch.setattr(settings, "max_photos_per_submission", 2)
    for _ in range(2):
        submission_service.attach_photo_to_submission(
            db, explore_submission.id, f"client-{uuid4().hex}", _FAKE_JPEG,
            content_type="image/jpeg", original_filename="a.jpg", storage=get_photo_storage(),
        )
    with pytest.raises(submission_service.TooManyPhotosError):
        submission_service.attach_photo_to_submission(
            db, explore_submission.id, f"client-{uuid4().hex}", _FAKE_JPEG,
            content_type="image/jpeg", original_filename="a.jpg", storage=get_photo_storage(),
        )
    photos = submission_service.list_submission_photos(db, explore_submission.id)
    assert len(photos) == 2  # the rejected attempt never got persisted


def test_build_submission_read_includes_all_photos(db, explore_submission):
    submission_service.attach_photo_to_submission(
        db, explore_submission.id, f"client-{uuid4().hex}", _FAKE_JPEG,
        content_type="image/jpeg", original_filename="a.jpg", storage=get_photo_storage(),
    )
    submission_service.attach_photo_to_submission(
        db, explore_submission.id, f"client-{uuid4().hex}", _FAKE_JPEG,
        content_type="image/jpeg", original_filename="b.jpg", storage=get_photo_storage(),
    )
    read = submission_service.build_submission_read(db, explore_submission)
    assert len(read.photos) == 2
    assert {p.original_filename for p in read.photos} == {"a.jpg", "b.jpg"}


def test_storage_failure_surfaces_as_media_storage_error_not_swallowed(db, explore_submission):
    """The root-cause fix: a storage backend failure must propagate as a
    clean, catchable MediaStorageError -- never swallowed, never an opaque
    unrelated success. Simulates the "mushroom photo" failure mode: a small,
    perfectly valid image that the storage backend itself rejects."""

    class _FailingStorage(MediaStorage):
        def save(self, content: bytes, original_filename: str) -> StoredFile:
            raise MediaStorageError("Could not store the uploaded file (storage backend rejected it: simulated failure).")

        def read_bytes(self, storage_key: str) -> bytes:
            raise FileNotFoundError

    with pytest.raises(MediaStorageError):
        submission_service.attach_photo_to_submission(
            db, explore_submission.id, f"client-{uuid4().hex}", _FAKE_JPEG,
            content_type="image/jpeg", original_filename="a.jpg", storage=_FailingStorage(),
        )
    # No photo row was left behind by the failed attempt.
    assert submission_service.list_submission_photos(db, explore_submission.id) == []


def test_route_maps_media_storage_error_to_502(db, explore_submission, monkeypatch):
    """End-to-end through the real HTTP route: a storage failure must reach
    the client as a clean 502 with a safe message, never a raw 500 with no
    diagnostic content (the exact gap that made the mushroom-photo bug
    invisible before this fix)."""

    class _FailingStorage(MediaStorage):
        def save(self, content: bytes, original_filename: str) -> StoredFile:
            raise MediaStorageError("Could not store the uploaded file (storage backend rejected it: simulated failure).")

        def read_bytes(self, storage_key: str) -> bytes:
            raise FileNotFoundError

    monkeypatch.setattr(
        "app.api.routes.submissions.get_photo_storage", lambda: _FailingStorage()
    )
    response = client.post(
        f"/api/v1/submissions/{explore_submission.id}/photo",
        files={"file": ("a.jpg", _FAKE_JPEG, "image/jpeg")},
        data={"client_photo_id": str(uuid4())},
    )
    assert response.status_code == 502
    assert "simulated failure" in response.json()["detail"]


def test_route_maps_too_many_photos_to_409(db, explore_submission, monkeypatch):
    monkeypatch.setattr(settings, "max_photos_per_submission", 1)
    first = client.post(
        f"/api/v1/submissions/{explore_submission.id}/photo",
        files={"file": ("a.jpg", _FAKE_JPEG, "image/jpeg")},
        data={"client_photo_id": str(uuid4())},
    )
    assert first.status_code == 201
    second = client.post(
        f"/api/v1/submissions/{explore_submission.id}/photo",
        files={"file": ("b.jpg", _FAKE_JPEG, "image/jpeg")},
        data={"client_photo_id": str(uuid4())},
    )
    assert second.status_code == 409


def test_route_response_lists_multiple_photos(db, explore_submission):
    r1 = client.post(
        f"/api/v1/submissions/{explore_submission.id}/photo",
        files={"file": ("a.jpg", _FAKE_JPEG, "image/jpeg")},
        data={"client_photo_id": str(uuid4())},
    )
    assert r1.status_code == 201
    r2 = client.post(
        f"/api/v1/submissions/{explore_submission.id}/photo",
        files={"file": ("b.jpg", _FAKE_JPEG, "image/jpeg")},
        data={"client_photo_id": str(uuid4())},
    )
    assert r2.status_code == 201
    assert len(r2.json()["photos"]) == 2


def test_supabase_storage_error_is_logged_and_wrapped(monkeypatch):
    """Unit-level check on SupabaseMediaStorage.save() itself: a real
    storage3 StorageApiError must become a MediaStorageError, never an
    uncaught exception -- this used to have NO error handling at all."""
    from app.services.storage.supabase_storage import SupabaseMediaStorage
    from storage3.exceptions import StorageApiError

    storage = SupabaseMediaStorage.__new__(SupabaseMediaStorage)
    storage._bucket = "photo-uploads"
    storage._known_extensions = frozenset({".jpg"})

    class _FailingBucket:
        def upload(self, **kwargs):
            raise StorageApiError("Bucket not found", code="404", status=404)

    class _FailingClientStorage:
        def from_(self, bucket):
            return _FailingBucket()

    class _FailingClient:
        storage = _FailingClientStorage()

    storage._client = _FailingClient()

    with pytest.raises(MediaStorageError) as exc_info:
        storage.save(_FAKE_JPEG, "a.jpg")
    assert "rejected it" in exc_info.value.message
