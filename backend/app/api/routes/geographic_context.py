from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.geographic_context import GeographicContext
from app.services import geographic_context as geographic_context_service

router = APIRouter(prefix="/api/v1/geographic-context", tags=["geographic-context"])


@router.get("", response_model=GeographicContext)
def get_geographic_context(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    db: Session = Depends(get_db),
):
    return geographic_context_service.resolve_geographic_context(db, latitude, longitude)
