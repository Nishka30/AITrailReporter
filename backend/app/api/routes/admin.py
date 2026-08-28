"""Admin API namespace (Content Curation & Moderation layer). Every route
here requires the minimal dev-safe admin token (see app/core/admin_auth.py).
This is additive to the existing API surface -- nothing here modifies or
depends on mobile-facing routes, and nothing here creates a second knowledge
database: every read goes through the existing PostgreSQL tables via
SQLAlchemy, joined explicitly in app/services/admin_*.py, the same way every
other service in this codebase works.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.admin_auth import AdminPrincipal, require_admin
from app.db.session import get_db
from app.schemas.admin import (
    AdminOverview,
    AdminQuestionSummary,
    ContributorDetail,
    ContributorSummary,
    PlaceDetail,
    PlaceSummary,
    ReviewDetail,
    ReviewQueueResult,
)
from app.schemas.observation_moderation import (
    ChangeModerationDecisionRequest,
    ObservationModerationRead,
    RejectObservationRequest,
)
from app.services import admin_contributors as contributor_service
from app.services import admin_overview as overview_service
from app.services import admin_places as place_service
from app.services import admin_questions as question_service
from app.services import admin_review as review_service
from app.services import observation_moderation as moderation_service
from app.services import submissions as submission_service
from app.services.storage import get_audio_storage, get_photo_storage

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.post("/auth/verify")
def verify_admin_token(admin: AdminPrincipal = Depends(require_admin)):
    """Used by the admin frontend's login screen to check a token before
    storing it -- performs no side effect beyond the auth check itself."""
    return {"ok": True, "name": admin.name}


@router.get("/overview", response_model=AdminOverview)
def get_overview(
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return overview_service.get_overview(db)


@router.get("/review-queue", response_model=ReviewQueueResult)
def get_review_queue(
    status: str = Query(default="pending_review"),
    knowledge_type: str | None = Query(default=None),
    safety_critical: bool | None = Query(default=None),
    guide_id: UUID | None = Query(default=None),
    place_id: UUID | None = Query(default=None),
    source_type: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=255),
    sort: str = Query(default="created_at"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    filters = review_service.ReviewQueueFilters(
        status=status or None,
        knowledge_type=knowledge_type,
        safety_critical=safety_critical,
        guide_id=guide_id,
        place_id=place_id,
        source_type=source_type,
        q=q,
        sort=sort,
    )
    return review_service.list_review_queue(db, filters, page, page_size)


@router.get("/knowledge", response_model=ReviewQueueResult)
def get_knowledge(
    status: str | None = Query(default=None),
    knowledge_type: str | None = Query(default=None),
    safety_critical: bool | None = Query(default=None),
    guide_id: UUID | None = Query(default=None),
    place_id: UUID | None = Query(default=None),
    source_type: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=255),
    sort: str = Query(default="observed_at"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Browses ALL observations regardless of moderation status (unlike
    /review-queue, which defaults to 'pending_review') -- the same knowledge
    a future public app would eventually read a filtered ('approved') slice
    of, see app/services/admin_review.py."""
    filters = review_service.ReviewQueueFilters(
        status=status,
        knowledge_type=knowledge_type,
        safety_critical=safety_critical,
        guide_id=guide_id,
        place_id=place_id,
        source_type=source_type,
        q=q,
        sort=sort,
    )
    return review_service.list_review_queue(db, filters, page, page_size)


@router.get("/reviews/{observation_id}", response_model=ReviewDetail)
@router.get("/knowledge/{observation_id}", response_model=ReviewDetail)
def get_review_detail(
    observation_id: UUID,
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    detail = review_service.get_review_detail(db, observation_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Observation not found")
    return detail


@router.post("/reviews/{observation_id}/approve", response_model=ObservationModerationRead)
def approve_observation(
    observation_id: UUID,
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return moderation_service.approve(db, observation_id, admin.name)
    except moderation_service.ModerationNotFoundError:
        raise HTTPException(status_code=404, detail="Observation not found")
    except moderation_service.AlreadyDecidedError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                "This observation was already rejected. Use "
                "POST /reviews/{observation_id}/change-decision to switch it."
            ),
        )


@router.post("/reviews/{observation_id}/reject", response_model=ObservationModerationRead)
def reject_observation(
    observation_id: UUID,
    payload: RejectObservationRequest,
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return moderation_service.reject(
            db, observation_id, admin.name, payload.reason, payload.note
        )
    except moderation_service.ModerationNotFoundError:
        raise HTTPException(status_code=404, detail="Observation not found")
    except moderation_service.AlreadyDecidedError:
        raise HTTPException(
            status_code=409,
            detail=(
                "This observation was already approved. Use "
                "POST /reviews/{observation_id}/change-decision to switch it."
            ),
        )


@router.post("/reviews/{observation_id}/change-decision", response_model=ObservationModerationRead)
def change_observation_decision(
    observation_id: UUID,
    payload: ChangeModerationDecisionRequest,
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Explicitly switches an already-decided observation to the opposite
    decision -- a deliberate, separate action from approve/reject (see
    app/services/observation_moderation.py:change_decision)."""
    try:
        return moderation_service.change_decision(
            db, observation_id, admin.name, payload.status, payload.reason, payload.note
        )
    except moderation_service.ModerationNotFoundError:
        raise HTTPException(status_code=404, detail="Observation not found")
    except moderation_service.NotYetDecidedError:
        raise HTTPException(
            status_code=409,
            detail=(
                "This observation has not been decided yet. Use "
                "POST /reviews/{observation_id}/approve or /reject instead."
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/places", response_model=list[PlaceSummary])
def list_places(
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return place_service.list_places(db)


@router.get("/places/{location_id}", response_model=PlaceDetail)
def get_place(
    location_id: UUID,
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    place = place_service.get_place_detail(db, location_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    return place


@router.get("/contributors", response_model=list[ContributorSummary])
def list_contributors(
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return contributor_service.list_contributors(db)


@router.get("/contributors/{guide_id}", response_model=ContributorDetail)
def get_contributor(
    guide_id: UUID,
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    contributor = contributor_service.get_contributor_detail(db, guide_id)
    if contributor is None:
        raise HTTPException(status_code=404, detail="Contributor not found")
    return contributor


@router.get("/questions", response_model=list[AdminQuestionSummary])
def list_questions(
    status: str | None = Query(default=None),
    assignment_status: str | None = Query(default=None),
    safety_critical: bool | None = Query(default=None),
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return question_service.list_admin_questions(db, status, assignment_status, safety_critical)


@router.get("/submissions/{submission_id}/audio")
def get_submission_audio(
    submission_id: UUID,
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Streams a submission's audio evidence for the Review Detail player.
    Never exposes the raw storage_key/path to the client -- read server-side
    through the same MediaStorage abstraction used for upload. Uses
    read_bytes() (not resolve_path()), the interface both the local-
    filesystem AND Supabase Storage backends actually implement -- see
    app/services/storage/base.py."""
    submission = submission_service.get_submission(db, submission_id)
    if submission is None or submission.audio is None:
        raise HTTPException(status_code=404, detail="No audio attached to this submission")
    try:
        content = get_audio_storage().read_bytes(submission.audio_storage_key)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Audio file is missing on the server")
    return Response(content=content, media_type=submission.audio.content_type)


@router.get("/submissions/{submission_id}/photo")
def get_submission_photo(
    submission_id: UUID,
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    submission = submission_service.get_submission(db, submission_id)
    if submission is None or submission.photo is None:
        raise HTTPException(status_code=404, detail="No photo attached to this submission")
    try:
        content = get_photo_storage().read_bytes(submission.photo_storage_key)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Photo file is missing on the server")
    return Response(content=content, media_type=submission.photo.content_type)
