from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.db.models.guide import Guide
from app.db.session import get_db
from app.schemas.guide_location import GuideLocationCreate, GuideLocationRead
from app.services import guide_locations as guide_location_service
from app.services import guides as guide_service

router = APIRouter(prefix="/api/v1/guides/{guide_id}/locations", tags=["guide-locations"])


def get_guide_or_404(guide_id: UUID, db: Session = Depends(get_db)) -> Guide:
    guide = guide_service.get_guide(db, guide_id)
    if guide is None:
        raise HTTPException(status_code=404, detail="Guide not found")
    return guide


@router.post("", response_model=GuideLocationRead, status_code=201)
def submit_location(
    guide_id: UUID,
    payload: GuideLocationCreate,
    response: Response,
    guide: Guide = Depends(get_guide_or_404),
    db: Session = Depends(get_db),
):
    """Records a GPS sample. Idempotent when payload.client_location_id is supplied:
    a repeat request with the same id and matching data returns the existing sample
    with 200 instead of creating a duplicate. The same id with different data is
    rejected with 409 rather than silently overwriting the original."""
    try:
        location, created = guide_location_service.create_or_get_location(db, guide.id, payload)
    except guide_location_service.LocationConflictError:
        raise HTTPException(
            status_code=409,
            detail="client_location_id was already used with different location data",
        )

    response.status_code = 201 if created else 200
    return location


@router.get("/latest", response_model=GuideLocationRead)
def get_latest_location(
    guide_id: UUID,
    guide: Guide = Depends(get_guide_or_404),
    db: Session = Depends(get_db),
):
    location = guide_location_service.get_latest_location(db, guide_id)
    if location is None:
        raise HTTPException(status_code=404, detail="No location recorded for this guide")
    return location


@router.get("", response_model=list[GuideLocationRead])
def list_locations(
    guide_id: UUID,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    guide: Guide = Depends(get_guide_or_404),
    db: Session = Depends(get_db),
):
    return guide_location_service.list_locations(db, guide_id, limit, offset)
