"""Public traveller website API (/api/v1/public/*). No authentication --
this is the ONLY route group meant to be called from an arbitrary browser
origin (see settings.public_cors_origins / app/main.py). Every read here
goes through app/services/public_content.py, which hard-filters to
ObservationModeration.status == 'approved'. Nothing in this file may ever
return a Guide's phone number, a raw storage key, or a pending/rejected
Observation."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import public_content as public_service
from app.services import submissions as submission_service
from app.services.storage import get_audio_storage, get_photo_storage

from app.db.models.observation import Observation
from app.db.models.observation_moderation import ObservationModeration
from app.schemas.public import (
    PublicKnowledgeType,
    PublicLocationDetail,
    PublicLocationSummary,
    PublicObservation,
    PublicObservationList,
    PublicSearchResult,
)

router = APIRouter(prefix="/api/v1/public", tags=["public"])


@router.get("/locations", response_model=list[PublicLocationSummary])
def list_locations(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return public_service.list_public_locations(db, limit=limit)


@router.get("/locations/{location_id}", response_model=PublicLocationDetail)
def get_location(
    location_id: UUID,
    db: Session = Depends(get_db),
):
    detail = public_service.get_public_location_detail(
        db, location_id, datetime.now(timezone.utc)
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="Place not found")
    return detail


@router.get("/observations", response_model=PublicObservationList)
def list_observations(
    location_id: UUID | None = Query(default=None),
    knowledge_type: str | None = Query(default=None),
    has_photo: bool | None = Query(default=None),
    has_audio: bool | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return public_service.list_public_observations(
        db,
        location_id=location_id,
        knowledge_type=knowledge_type,
        has_photo=has_photo,
        has_audio=has_audio,
        limit=limit,
        offset=offset,
    )


@router.get("/observations/{observation_id}", response_model=PublicObservation)
def get_observation(
    observation_id: UUID,
    db: Session = Depends(get_db),
):
    observation = public_service.get_public_observation(db, observation_id)
    if observation is None:
        raise HTTPException(status_code=404, detail="Observation not found")
    return observation


@router.get("/knowledge-types", response_model=list[PublicKnowledgeType])
def list_knowledge_types(db: Session = Depends(get_db)):
    return public_service.list_public_knowledge_types(db)


@router.get("/search", response_model=PublicSearchResult)
def search(
    q: str = Query(min_length=1, max_length=255),
    db: Session = Depends(get_db),
):
    return public_service.search_public(db, q)


def _submission_has_approved_observation(db: Session, submission_id: UUID) -> bool:
    stmt = (
        select(Observation.id)
        .join(ObservationModeration, ObservationModeration.observation_id == Observation.id)
        .where(Observation.submission_id == submission_id, ObservationModeration.status == "approved")
        .limit(1)
    )
    return db.execute(stmt).first() is not None


@router.get("/media/{submission_id}/photo")
def get_public_photo(submission_id: UUID, db: Session = Depends(get_db)):
    """Streams a photo ONLY when the submission it belongs to produced at
    least one approved observation -- same reasoning as
    app/api/routes/admin.py's equivalent route, plus the approval gate. A
    submission with unapproved-only observations 404s, indistinguishable
    from a submission that doesn't exist, so this endpoint never confirms
    the existence of unapproved content."""
    submission = submission_service.get_submission(db, submission_id)
    if submission is None or submission.photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    if not _submission_has_approved_observation(db, submission_id):
        raise HTTPException(status_code=404, detail="Photo not found")
    try:
        content = get_photo_storage().read_bytes(submission.photo_storage_key)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Photo not found")
    return Response(content=content, media_type=submission.photo.content_type)


@router.get("/media/{submission_id}/audio")
def get_public_audio(submission_id: UUID, db: Session = Depends(get_db)):
    submission = submission_service.get_submission(db, submission_id)
    if submission is None or submission.audio is None:
        raise HTTPException(status_code=404, detail="Audio not found")
    if not _submission_has_approved_observation(db, submission_id):
        raise HTTPException(status_code=404, detail="Audio not found")
    try:
        content = get_audio_storage().read_bytes(submission.audio_storage_key)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Audio not found")
    return Response(content=content, media_type=submission.audio.content_type)
